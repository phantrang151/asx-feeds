# ASX Agent - local setup

Two pieces run together locally: the Python backend (LangGraph agents + a small
FastAPI server) and the Next.js frontend.

## 1. Supabase project

1. Create a project at supabase.com.
2. Run `schema.sql` in the Supabase SQL editor (creates all tables, indexes, the
   `match_feeds` function, and Row Level Security policies).
3. Note down, from Project Settings > API:
   - Project URL
   - `anon` public key (frontend)
   - `service_role` key (backend only - never put this in frontend code)
   - JWT Secret (backend, to verify frontend requests)
4. From Project Settings > Database, note down the direct Postgres connection string
   (for `SUPABASE_DB_URL` - used by the long-term memory store/checkpointer).

## 2. Backend

```
cp .env.example .env
# fill in GROQ_API_KEY, SUPABASE_URL, SUPABASE_KEY (service_role), SUPABASE_DB_URL,
# SUPABASE_JWT_SECRET

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

This serves `POST /api/feeds` (feed creation, the one write that needs a server-side
embedding) on `http://localhost:8000`.

To exercise the agents directly (outside the UI): `python -m scripts.seed_single_user`
and `python -m scripts.test_conduct_analysis`. Both use `TEST_USER_ID` from `config.py` -
since `feeds.user_id` now has a foreign key to `auth.users`, that id must be a REAL user.
Sign up once through the frontend, then copy that user's id (Supabase dashboard >
Authentication > Users) into `TEST_USER_ID`.

## 3. Frontend

```
cd frontend
cp .env.local.example .env.local
# fill in NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY

npm install
npm run dev
```

Open http://localhost:3000 - it redirects to `/signup` if you're not signed in yet.

## Run on localbrowser
Terminal 1 — backend:

cd d:\Trang\GenAI_Projects\asx-agent
asx_feed_env\Scripts\activate
uvicorn app.main:app --reload --port 8000
Wait for Application startup complete.

Terminal 2 — frontend:
cd d:\Trang\GenAI_Projects\asx-agent\frontend
npm run dev
Then open http://localhost:3000 in your browser.

## Flow
1. Sign up with email/password
2. Add a ticker to your watchlist
3. Create a feed for that ticker (name + description) - this calls the FastAPI backend,
   which embeds the description and stores it
4. Run `python -m scripts.seed_single_user` (with `TEST_USER_ID` set to your real user id)
   to populate some classified news into your feeds
5. Visit `/alerts` to see the classified items
