import jwt
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import SUPABASE_JWT_SECRET
from tools.embeddings import embed
from db.queries import create_feed

app = FastAPI(title="ASX Agent API")

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


def get_user_id_from_token(authorization: str = Header(...)) -> str:
    """
    Verifies the Supabase-issued JWT the frontend sends (from the user's active session)
    and returns the user id it was issued for. This is what lets the API act on behalf of
    'whoever is currently logged in' without the frontend ever sending a user_id directly -
    the user_id always comes from a verified token, not from a form field a client could
    tamper with.
    """
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET is not configured")

    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(
            token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated"
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


@app.get("/health")
def health():
    return {"status": "ok"}
