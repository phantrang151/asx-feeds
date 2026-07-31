import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.auth import require_admin
from agent.pipelines.orchestrator import run_ingestion_for_all_watchlisted_tickers
from db.client import get_client
from db.storage import DOCUMENTS_BUCKET
from db.queries import (
    get_recent_pipeline_runs,
    insert_document,
    update_document_storage_path,
    update_document_status,
    insert_document_chunks,
    get_documents_for_ticker,
    get_document_chunk_counts,
)
from monitoring.langsmith_summary import get_langsmith_summary
from tools.documents import extract_text, chunk_text, fetch_link
from tools.embeddings import embed_batch

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Same ASX ticker format TickerForm.js enforces client-side - re-checked here since this
# is a new server-side entry point a client-side check alone can't be trusted to gate.
ASX_TICKER_PATTERN = re.compile(r"^[A-Z0-9]{1,6}\.AX$")

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


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


def _safe_storage_name(title: str) -> str:
    """Storage paths can't safely hold arbitrary title text - a link's title IS its full
    URL (slashes, colons), which would otherwise create broken/deeply-nested objects."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", title)[:100]


def _process_document(
    ticker: str, title: str, source_type: str, source_url: str | None,
    raw: bytes, content_type: str | None, uploaded_by: str,
) -> dict:
    """Store -> upload raw bytes -> extract -> chunk -> embed -> mark ready/failed for one
    file or link. Called once per item from the batch endpoint below, each wrapped in its
    own try/except there so one bad item can't take down the rest of the batch - same
    per-item error isolation as agent/pipelines/orchestrator.py's per-ticker try/except."""
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"File exceeds the {MAX_DOCUMENT_BYTES // (1024 * 1024)}MB limit.")

    doc = insert_document(ticker, title, source_type, source_url, uploaded_by)
    try:
        storage_path = f"{ticker}/{doc['id']}-{_safe_storage_name(title)}"
        get_client().storage.from_(DOCUMENTS_BUCKET).upload(
            storage_path, raw, file_options={"content-type": content_type or "application/octet-stream"}
        )
        update_document_storage_path(doc["id"], storage_path)

        text = extract_text(raw, content_type, title)
        chunks = chunk_text(text)
        if not chunks:
            update_document_status(doc["id"], "failed", "No extractable text found")
            return {"title": title, "status": "failed", "error": "No extractable text found"}

        embeddings = embed_batch(chunks)
        insert_document_chunks(doc["id"], ticker, chunks, embeddings)
        update_document_status(doc["id"], "ready")
        return {"title": title, "status": "ready", "document_id": doc["id"], "chunk_count": len(chunks)}
    except Exception as e:
        update_document_status(doc["id"], "failed", str(e))
        return {"title": title, "status": "failed", "error": str(e)}


@router.post("/documents/upload")
def upload_documents(
    ticker: str = Form(...),
    links: str = Form(""),
    files: list[UploadFile] = File([]),
    admin_user_id: str = Depends(require_admin),
):
    """Bulk upload: any mix of files and pasted links (newline-separated) for one ticker,
    each run through _process_document independently - one bad file or dead link doesn't
    abort the rest of the batch."""
    ticker = ticker.strip().upper()
    if not ASX_TICKER_PATTERN.match(ticker):
        raise HTTPException(status_code=422, detail="Ticker must be a Yahoo Finance ASX symbol, e.g. TLS.AX.")

    results = []

    for f in files:
        try:
            raw = f.file.read()
            results.append(_process_document(ticker, f.filename, "file", None, raw, f.content_type, admin_user_id))
        except Exception as e:
            results.append({"title": f.filename, "status": "failed", "error": str(e)})

    for url in [u.strip() for u in links.splitlines() if u.strip()]:
        try:
            raw, content_type = fetch_link(url)
            results.append(_process_document(ticker, url, "link", url, raw, content_type, admin_user_id))
        except Exception as e:
            results.append({"title": url, "status": "failed", "error": str(e)})

    return {"ticker": ticker, "results": results}


@router.get("/documents")
def list_documents(ticker: str, admin_user_id: str = Depends(require_admin)):
    ticker = ticker.strip().upper()
    docs = get_documents_for_ticker(ticker)
    counts = get_document_chunk_counts(ticker)
    for d in docs:
        d["chunk_count"] = counts.get(d["id"], 0)
    return docs
