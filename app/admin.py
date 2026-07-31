from fastapi import APIRouter, Depends

from app.auth import require_admin
from agent.pipelines.orchestrator import run_ingestion_for_all_watchlisted_tickers
from db.queries import get_recent_pipeline_runs
from monitoring.langsmith_summary import get_langsmith_summary

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/me")
def admin_me(admin_user_id: str = Depends(require_admin)):
    """Lets the frontend check 'is this user an admin' (to decide whether to even show the
    Admin nav link) without duplicating the ADMIN_EMAILS allowlist client-side. Every other
    route here already 403s a non-admin via require_admin - this just exposes that check on
    its own with no other side effect."""
    return {"is_admin": True}


@router.post("/pipeline/trigger")
def trigger_pipeline(admin_user_id: str = Depends(require_admin)):
    """Runs the ingestion pipeline for every watchlisted ticker right now, synchronously,
    and returns the summary. See orchestrator.py for why this is a blocking call for now."""
    return run_ingestion_for_all_watchlisted_tickers()


@router.get("/pipeline/runs")
def list_pipeline_runs(admin_user_id: str = Depends(require_admin)):
    """Recent pipeline run history - what the admin dashboard's run log renders."""
    return get_recent_pipeline_runs(limit=20)


@router.get("/langsmith/summary")
def langsmith_summary(admin_user_id: str = Depends(require_admin)):
    """Cost/latency/error summary over the last 24h of traced LLM calls. Model QUALITY
    metrics (accuracy, relevance, groundedness, etc.) are intentionally not included here
    yet - those need to be defined first (see the note in the admin page)."""
    return get_langsmith_summary()
