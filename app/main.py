import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from anthropic import APIStatusError as AnthropicAPIStatusError
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

from config import TOKEN_CEILING_WINDOW_HOURS
from tools.embeddings import embed
from db.queries import (
    create_feed,
    get_common_feed_template,
    update_feed,
    set_feed_needs_rematch,
    log_token_usage,
    sum_recent_token_usage,
    insert_request_trace,
    insert_request_trace_steps,
    insert_ops_alert,
)
from db.storage import ensure_documents_bucket
from agent.chat.graph import graph
from agent.guardrails.rate_limit import enforce_rate_limit
from agent.guardrails.daily_token_budget import enforce_daily_token_budget, DAILY_BUDGET_MESSAGE
from agent.guardrails.token_budget import DailyTokenBudgetExceededError
from agent.guardrails.citations import filter_reachable_references
from agent.guardrails.tracer import RequestTracer
from agent.guardrails.alerts import evaluate_alerts
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

# Local Next.js dev server (:3000) and the deployed frontend on Azure Static Web Apps.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://orange-tree-0cfeca100.7.azurestaticapps.net",
        "https://asx-feed.trang-phan.com",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)


@app.on_event("startup")
def on_startup():
    ensure_documents_bucket()


@app.exception_handler(AnthropicAPIStatusError)
async def anthropic_error_handler(request: Request, exc: AnthropicAPIStatusError):
    """
    Every LLM call in this app goes through Claude, so its failures are common enough (daily
    token-quota exhaustion especially, during heavy testing/demo use) to deserve a specific,
    actionable message instead of falling through to the generic "Internal server error"
    below - the frontend already just displays whatever `detail` it gets. Registered by type
    (not the bare Exception class), so it stays in ExceptionMiddleware, inside CORSMiddleware.
    """
    logger.warning("Anthropic API error on %s %s: %s", request.method, request.url.path, exc)
    if exc.status_code == 429:
        detail = "The AI model's usage limit has been reached for now - please try again in a bit."
    elif exc.type == "overloaded_error":
        detail = "The AI model is temporarily overloaded - please try again shortly."
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
    # Raises 429 up front if this user has already used up today's token budget;
    # otherwise a fresh callback seeded with today's REMAINING allowance, shared via
    # configurable with every node that calls an LLM (router, conduct_analysis, and its
    # advice-check judge) so it also trips mid-request if this request alone would
    # cross the daily line (see agent/guardrails/daily_token_budget.py).
    daily_cb = enforce_daily_token_budget(user_id)
    # One RequestTracer per request (see agent/guardrails/tracer.py) - records every
    # LLM/tool call's timing/tokens automatically via the callback hooks, plus the two
    # regex guardrail checks manually - and is bulk-written to request_trace_steps
    # below regardless of how the request ends.
    tracer = RequestTracer()
    request_start = time.monotonic()
    config = {
        "configurable": {
            "thread_id": req.thread_id,
            "langgraph_user_id": user_id,
            "daily_token_cb": daily_cb,
            "tracer": tracer,
        }
    }

    response = None
    status = "completed"
    decline_reason = None
    daily_budget_exceeded = False
    try:
        response = graph.invoke({"messages": [HumanMessage(content=req.question)]}, config=config)
        if response.get("category") == "declined":
            status = "declined"
            decline_reason = response.get("result")
    except DailyTokenBudgetExceededError:
        status = "error"
        decline_reason = "daily_token_budget_exceeded"
        daily_budget_exceeded = True
    except Exception:
        # Still recorded below (whatever the tracer captured before the crash) before
        # re-raising for UnhandledExceptionMiddleware to turn into the standard 500 -
        # an unexpected failure shouldn't also mean losing its trace.
        status = "error"
        decline_reason = "unhandled_exception"
        raise
    finally:
        total_duration_ms = round((time.monotonic() - request_start) * 1000)
        # Logged regardless of outcome (success, in-graph decline, or the 429 above) so
        # tokens actually spent before an abort still count against today's total - Groq
        # already billed for them even if the request didn't finish.
        if daily_cb.total_tokens:
            log_token_usage(user_id, daily_cb.total_tokens)

        trace_row = insert_request_trace(
            user_id=user_id,
            thread_id=req.thread_id,
            question=req.question,
            ticker=response.get("ticker") if response else None,
            category=response.get("category") if response else None,
            status=status,
            decline_reason=decline_reason,
            input_guardrail_regex_matched=response.get("input_guardrail_regex_matched") if response else None,
            input_guardrail_llm_is_advice=response.get("input_guardrail_llm_is_advice") if response else None,
            output_guardrail_regex_matched=response.get("output_guardrail_regex_matched") if response else None,
            output_guardrail_llm_is_advice=response.get("output_guardrail_llm_is_advice") if response else None,
            evidence_count=response.get("evidence_count") if response else None,
            step_count=tracer.step_count,
            total_tokens=daily_cb.total_tokens or None,
            total_duration_ms=total_duration_ms,
            # Only meaningful for a completed conduct_analysis request - what
            # eval/run_live_sample_eval.py re-judges later against real traffic.
            answer=response["messages"][-1].content if response and status == "completed" else None,
            evidence=response.get("evidence") if response and status == "completed" else None,
        )
        insert_request_trace_steps(trace_row["id"], tracer.steps)

        # Trailing-day total AFTER this request's own usage was just logged above - what
        # this user's NEXT request would be checked against by enforce_daily_token_budget.
        since = (datetime.now(timezone.utc) - timedelta(hours=TOKEN_CEILING_WINDOW_HOURS)).isoformat()
        daily_tokens_after = sum_recent_token_usage(user_id, since)
        alerts = evaluate_alerts(
            request_tokens=daily_cb.total_tokens or None,
            daily_tokens_after=daily_tokens_after or None,
            step_count=tracer.step_count,
            duration_ms=total_duration_ms,
        )
        for alert in alerts:
            insert_ops_alert(trace_row["id"], user_id, **alert)

    if daily_budget_exceeded:
        raise HTTPException(status_code=429, detail=DAILY_BUDGET_MESSAGE)

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
