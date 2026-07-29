import jwt
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from jwt import PyJWKClient
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from config import SUPABASE_URL
from tools.embeddings import embed
from db.queries import create_feed
from agent.chat.graph import graph

app = FastAPI(title="ASX Agent API")

# Supabase now signs session tokens with an asymmetric key (ES256) rather than a shared
# HS256 secret, so verification uses the project's public JWKS instead of
# SUPABASE_JWT_SECRET. PyJWKClient caches fetched keys and looks one up by the token's kid.
_jwks_client = PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json")

# Local-only CORS setup: the Next.js dev server runs on :3000, this API on :8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class FeedCreateRequest(BaseModel):
    ticker: str
    feed_name: str
    feed_description: str


class AskRequest(BaseModel):
    question: str
    thread_id: str


def get_user_id_from_token(authorization: str = Header(...)) -> str:
    """
    Verifies the Supabase-issued JWT the frontend sends (from the user's active session)
    and returns the user id it was issued for. This is what lets the API act on behalf of
    'whoever is currently logged in' without the frontend ever sending a user_id directly -
    the user_id always comes from a verified token, not from a form field a client could
    tamper with.
    """
    token = authorization.replace("Bearer ", "")
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token, signing_key.key, algorithms=["ES256"], audience="authenticated"
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")
    return payload["sub"]


@app.post("/api/feeds")
def create_feed_endpoint(req: FeedCreateRequest, authorization: str = Header(...)):
    """
    Creates a feed for the CURRENT logged-in user (from the verified token, not from the
    request body). Computing the embedding requires the Python sentence-transformers
    model, which is why this one write goes through the backend instead of a direct
    Supabase insert from the frontend - everything else (reading feeds/tickers/alerts,
    creating a ticker) doesn't need an embedding and goes straight to Supabase, guarded
    by RLS instead.
    """
    user_id = get_user_id_from_token(authorization)
    embedding = embed(req.feed_description)
    feed = create_feed(user_id, req.ticker, req.feed_name, req.feed_description, embedding)
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
    config = {"configurable": {"thread_id": req.thread_id, "langgraph_user_id": user_id}}
    response = graph.invoke({"messages": [HumanMessage(content=req.question)]}, config=config)
    return {
        "answer": response["messages"][-1].content,
        "ticker": response.get("ticker"),
        "category": response.get("category"),
    }


@app.get("/health")
def health():
    return {"status": "ok"}
