from typing import Optional
from supabase import ClientOptions, create_client, Client

from config import SUPABASE_URL, SUPABASE_KEY, DB_TIMEOUT

_client: Optional[Client] = None


def get_client() -> Client:
    """Lazily creates and reuses a single Supabase client for the process."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set in .env before using the database."
            )
        _client = create_client(SUPABASE_URL
                                , SUPABASE_KEY
                                ,options=ClientOptions(postgrest_client_timeout=DB_TIMEOUT)
                                )
    return _client
