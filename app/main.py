import logging
from typing import Literal, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from groq import APIStatusError as GroqAPIStatusError
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

from tools.embeddings import embed
from db.queries import create_feed, get_common_feed_template, update_feed, set_feed_needs_rematch
from db.storage import ensure_documents_bucket
from agent.chat.graph import graph
from agent.guardrails.rate_limit import enforce_rate_limit
from agent.guardrails.citations import filter_reachable_references
from app.auth import get_user_id_from_token
from app.admin import router as admin_router

logger = logging.getLogger(__name__)

app = FastAPI(title="ASX Agent API")


class UnhandledExceptionMiddleware(BaseHTTPMiddleware):
    """
    Starlette treats a handler registered via @app.exception_handler(Exception) as the
    500 "error_handler" and runs it inside ServerErrorMiddleware, which sits OUTSIDE every
    middleware added with app.add_middleware() (CORSMiddleware included) - so that response
    never gets Access-Control-Allow-Origin, and the browser reports an unrelated CORS/network
    failure instead of the actual 500, hiding the real error. Catching here instead, in a
    middleware added BEFORE CORSMiddleware (so CORSMiddleware wraps it, not the other way
    round), keeps the response inside the normal middleware chain so CORS headers get added.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.add_middleware(UnhandledExceptionMiddleware)

# Local-only CORS setup: the Next.js dev server runs on :3000, this API on :8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)


@app.on_event("startup")
def on_startup():
    ensure_documents_bucket()


@app.exception_handler(GroqAPIStatusError)
async def groq_error_handler(request: Request, exc: GroqAPIStatusError):
    """
    Every LLM call in this app goes through Groq, so its failures are common enough (daily
    token-quota exhaustion especially, during heavy testing/demo use) to deserve a specific,
    actionable message instead of falling through to the generic "Internal server error"
    below - the frontend already just displays whatever `detail` it gets. Registered by type
    (not the bare Exception class), so it stays in ExceptionMiddleware, inside CORSMiddleware.
    """
    logger.warning("Groq API error on %s %s: %s", request.method, request.url.path, exc)
    error_code = exc.body.get("error", {}).get("code") if isinstance(exc.body, dict) else None
    if exc.status_code == 429:
        detail = "The AI model's usage limit has been reached for now - please try again in a bit."
    elif error_code == "tool_use_failed":
        # Not an outage - Groq accepted the request but the model (usually the smaller
        # JUDGE_MODEL doing forced structured output, e.g. the advice-avoidance check)
        # emitted a malformed function call. Transient and retry-safe, but a distinct
        # cause from "model unreachable" - worth telling apart when debugging failures.
        detail = "The AI model produced a malformed response while judging the output - please try again."
    else:
        detail = "The AI model is temporarily unavailable - please try again shortly."
    return JSONResponse(status_code=503, content={"detail": detail})


class FeedCreateRequest(BaseModel):
    ticker: str
    feed_type: Literal["common", "custom"] = "custom"
    # Required when feed_type='common' (identifies which common_feed_templates row to
    # link to); feed_name/feed_description are required when feed_type='custom' and
    # ignored (derived from the template) when feed_type='common'.
    common_feed_template_id: Optional[str] = None
    feed_name: Optional[str] = None
    feed_description: Optional[str] = None


class FeedUpdateRequest(BaseModel):
    feed_name: Optional[str] = None
    feed_description: Optional[str] = None
    # UI only offers 10%-90% in steps of 10 - enforced here too since this is a
    # backend-authoritative field, not just a frontend constraint.
    match_threshold: Optional[float] = None

    @field_validator("match_threshold")
    @classmethod
    def _threshold_in_range(cls, v):
        if v is not None and not (0.1 <= v <= 0.9):
            raise ValueError("match_threshold must be between 0.1 and 0.9")
        return v


class AskRequest(BaseModel):
    question: str
    thread_id: str


@app.post("/api/feeds")
def create_feed_endpoint(req: FeedCreateRequest, authorization: str = Header(...)):
    """
    Creates a feed for the CURRENT logged-in user (from the verified token, not from the
    request body). Computing the embedding requires the Python sentence-transformers
    model, which is why this one write goes through the backend instead of a direct
    Supabase insert from the frontend - everything else (reading feeds/tickers/alerts,
    creating a ticker) doesn't need an embedding and goes straight to Supabase, guarded
    by RLS instead.

    For feed_type='common', the template's description + embedding are copied onto the
    feeds row instead of embedding user-supplied text - the LLM classification cost for
    common feeds is shared across every user via common_feed_items, computed once per
    ticker rather than once per user's feed.
    """
    user_id = get_user_id_from_token(authorization)

    if req.feed_type == "common":
        if not req.common_feed_template_id:
            raise HTTPException(status_code=422, detail="common_feed_template_id is required for common feeds.")
        template = get_common_feed_template(req.common_feed_template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Unknown common feed template.")
        feed = create_feed(
            user_id,
            req.ticker,
            template["name"],
            template["description"],
            template["description_embedding"],
            match_threshold=template["match_threshold"],
            feed_type="common",
            common_feed_template_id=template["id"],
        )
        return feed

    if not req.feed_name or not req.feed_description:
        raise HTTPException(status_code=422, detail="feed_name and feed_description are required for custom feeds.")
    embedding = embed(req.feed_description)
    feed = create_feed(user_id, req.ticker, req.feed_name, req.feed_description, embedding)
    return feed


@app.patch("/api/feeds/{feed_id}")
def update_feed_endpoint(feed_id: str, req: FeedUpdateRequest, authorization: str = Header(...)):
    """
    Edits a CUSTOM feed's name, description, and/or threshold. Common feeds mirror a
    shared common_feed_templates row and aren't user-editable, so update_feed() scopes to
    feed_type='custom' as well as ownership - either a common feed or one the caller
    doesn't own returns None here, surfaced as the same 404 (no need to distinguish "not
    yours" from "not editable" to the caller).

    Recomputes the embedding when feed_description changes, same as feed creation - this
    is why editing goes through the backend rather than a direct Supabase update from the
    frontend.
    """
    user_id = get_user_id_from_token(authorization)
    embedding = embed(req.feed_description) if req.feed_description else None
    feed = update_feed(
        feed_id,
        user_id,
        feed_name=req.feed_name,
        feed_description=req.feed_description,
        description_embedding=embedding,
        match_threshold=req.match_threshold,
    )
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found.")
    return feed


@app.post("/api/feeds/{feed_id}/refresh")
def refresh_feed_endpoint(feed_id: str, authorization: str = Header(...)):
    """
    Flags a CUSTOM feed so the next pipeline run wipes its feed_items and re-matches its
    entire ticker_news history under its current description/threshold - lets a user see
    the effect of an edit on past news, not just newly-fetched articles. Not synchronous:
    the actual re-match happens on the next scheduled or admin-triggered pipeline run (see
    classify_and_store_node).
    """
    user_id = get_user_id_from_token(authorization)
    feed = set_feed_needs_rematch(feed_id, user_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found.")
    return feed


@app.post("/api/ask")
def ask_endpoint(req: AskRequest, authorization: str = Header(...)):
    """
    Runs the chat/analysis agent graph (router -> search_news | conduct_analysis) for the
    CURRENT logged-in user and returns its final answer. thread_id scopes the LangGraph
    checkpointer to one chat session, so follow-up questions on the same thread keep
    conversation context - the frontend generates one id per page load and reuses it.
    """
    user_id = get_user_id_from_token(authorization)
    enforce_rate_limit(user_id)
    config = {"configurable": {"thread_id": req.thread_id, "langgraph_user_id": user_id}}
    response = graph.invoke({"messages": [HumanMessage(content=req.question)]}, config=config)
    # One choke point for references regardless of which node produced them (search_news
    # vs conduct_analysis) - nulls out `url` for anything unreachable so the frontend
    # never shows a dead link as a clickable source.
    references = filter_reachable_references(response.get("references") or [])
    return {
        "answer": response["messages"][-1].content,
        "ticker": response.get("ticker"),
        "category": response.get("category"),
        # Shown above the answer in the UI - the user sees what it's based on before
        # the (AI-generated, may-be-wrong) conclusion itself.
        "references": references,
    }


@app.get("/health")
def health():
    return {"status": "ok"}
