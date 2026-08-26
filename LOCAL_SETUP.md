# ASX Agent - local setup

Two pieces run together locally: the Python backend (LangGraph agents + a small
FastAPI server) and the Next.js frontend.

## 1. Supabase project

1. Create a project at supabase.com.
2. Run `schema.sql` in the Supabase SQL editor (creates all tables, indexes, the
   `match_feeds` function, and Row Level Security policies).
3. If the database was created before the company sector/peer lookup feature, also run
   `scripts/migration_company_sector.sql` in the Supabase SQL editor. This is safe to
   run repeatedly because every change is guarded with `if not exists`.
4. Note down, from Project Settings > API:
   - Project URL
   - `anon` public key (frontend)
   - `service_role` key (backend only - never put this in frontend code)
   - JWT Secret (backend, to verify frontend requests)
5. From Project Settings > Database, note down the direct Postgres connection string
   (for `SUPABASE_DB_URL` - used by the long-term memory store/checkpointer).

## 2. One-time backend setup

```
copy .env.example .env
# fill in ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY (service_role), SUPABASE_DB_URL,
# SUPABASE_JWT_SECRET

asx_feed_env\Scripts\activate
pip install -r requirements.txt
```

The repository already contains the expected virtual environment at
`asx_feed_env`. If it does not exist on a new machine, create it first:

```
py -3.11 -m venv asx_feed_env
asx_feed_env\Scripts\activate
pip install -r requirements.txt
```

## 3. One-time frontend setup

```
cd frontend
copy .env.local.example .env.local
# fill in NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
npm install
cd ..
```

The local `frontend/.env.local` must contain:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

This serves `POST /api/feeds` (feed creation, the one write that needs a server-side
embedding) on `http://localhost:8000`.

To exercise the agents directly (outside the UI): `python -m scripts.seed_single_user`
and `python -m scripts.test_conduct_analysis`. Both use `TEST_USER_ID` from `config.py` -
since `feeds.user_id` now has a foreign key to `auth.users`, that id must be a REAL user.
Sign up once through the frontend, then copy that user's id (Supabase dashboard >
Authentication > Users) into `TEST_USER_ID`.

## 4. Everyday startup on Windows

Open a terminal at the repository root:

```
cd /d d:\Trang\GenAI_Projects\asx-agent
```

Then run the one command below:

```
.\scripts\start_local.bat
```

The launcher opens two persistent terminal windows:

- **ASX backend**: FastAPI at `http://localhost:8000`
- **ASX frontend**: Next.js at `http://localhost:3000`

Keep both windows open while using the application. Open the app at
`http://localhost:3000`; it redirects to `/signup` if you are not signed in. The admin
page is at `http://localhost:3000/admin` after signing in with an account in
`ADMIN_EMAILS`.

To debug backend code such as the ingestion pipeline, stop the **ASX backend** terminal,
open VS Code's Run and Debug view, and start **FastAPI: Debug backend**. The debug
configuration deliberately uses port `8000`, which is the API URL used by the frontend.
Leave the **ASX frontend** terminal running. Do not run the normal backend terminal and
the debugger at the same time, because only one process can own port 8000.

If the current terminal is PowerShell, use:

```
cmd /c .\scripts\start_local.bat
```

To stop the application, close both **ASX backend** and **ASX frontend** terminal
windows. Do not close only the launcher window.

### Troubleshooting

- If `localhost:3000` refuses to connect, confirm the **ASX frontend** window shows
   `Ready` and that it is running from the `frontend` directory.
- If the page says it cannot reach the API, confirm the **ASX backend** window shows
   `Application startup complete`, then open `http://localhost:8000/health`. It should
   return `{"status":"ok"}`.
- If a port is already in use, close the old service terminal before running the
   launcher again, or identify the process with:

   ```
   netstat -ano | findstr ":8000 :3000"
   ```

For manual startup only, use two terminals:

Terminal 1 - backend:

```
cd d:\Trang\GenAI_Projects\asx-agent
asx_feed_env\Scripts\activate
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Wait for `Application startup complete`.

Terminal 2 - frontend:

```
cd d:\Trang\GenAI_Projects\asx-agent\frontend
npm run dev
```

Then open http://localhost:3000 in your browser. The local
`frontend/.env.local` must keep `NEXT_PUBLIC_API_URL=http://localhost:8000`.

## Flow
1. Sign up with email/password
2. Add a ticker to your watchlist
3. Create a feed for that ticker (name + description) - this calls the FastAPI backend,
   which embeds the description and stores it
4. Run `python -m scripts.seed_single_user` (with `TEST_USER_ID` set to your real user id)
   to populate some classified news into your feeds
5. Visit `/alerts` to see the classified items
