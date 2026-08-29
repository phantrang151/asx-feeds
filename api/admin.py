import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.auth import require_admin
from config import QUALITY_SAMPLE_WINDOW_HOURS
from agent.pipelines.insight_graph import synthesize_insight_for
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
    get_recent_eval_runs,
    get_efficiency_summary,
    get_recent_ops_alerts,
    get_all_watchlist_entries,
    get_quality_samples,
    mark_quality_sample_reviewed,
    get_guardrail_samples,
    mark_guardrail_sample_reviewed,
    get_classification_samples,
    mark_classification_sample_reviewed,
)
from agent.eval.runners.run_generation_eval import run_generation_eval, DEFAULT_FIXTURE as DEFAULT_GENERATION_EVAL_FIXTURE
from agent.eval.runners.run_insight_eval import run_insight_eval
from agent.eval.runners.run_feed_summary_eval import run_feed_summary_eval
from agent.eval.score_guardrails import (
    run_guardrail_eval,
    DEFAULT_INPUT_FIXTURE as DEFAULT_INPUT_GUARDRAIL_FIXTURE,
    DEFAULT_OUTPUT_FIXTURE as DEFAULT_OUTPUT_GUARDRAIL_FIXTURE,
)
from agent.eval.score_research_order import run_research_order_eval
from agent.eval.runners.run_live_sample_eval import run_live_sample_eval
from agent.eval.score_classification import run_classification_eval, DEFAULT_LABELS_PATH
from monitoring.langsmith_summary import get_langsmith_summary
from monitoring.quality_sampling import run_quality_sampling
from monitoring.guardrail_sampling import run_guardrail_sampling
from monitoring.classification_sampling import run_classification_sampling
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


@router.post("/pipeline/debug-planner")
def debug_planner(ticker: str, admin_user_id: str = Depends(require_admin)):
    """Reruns the insight planner for one ticker using existing classified news. This
    deliberately skips fetching and classification so an unchanged ticker can be
    breakpoint-tested without changing ingestion state."""
    ticker = ticker.strip().upper()
    if not ASX_TICKER_PATTERN.fullmatch(ticker):
        raise HTTPException(status_code=422, detail="Ticker must be a Yahoo Finance ASX symbol, e.g. CBA.AX.")

    user_ids = sorted({
        entry["user_id"]
        for entry in get_all_watchlist_entries()
        if entry["ticker"] == ticker
    })
    if not user_ids:
        raise HTTPException(status_code=404, detail=f"No users are watching {ticker}.")

    results = []
    for user_id in user_ids:
        try:
            synthesize_insight_for(user_id, ticker)
            results.append({"user_id": user_id, "status": "success"})
        except Exception as error:
            results.append({"user_id": user_id, "status": "failed", "error": str(error)})

    return {"ticker": ticker, "users_processed": len(user_ids), "results": results}


@router.get("/pipeline/runs")
def list_pipeline_runs(
    limit: int = 10,
    offset: int = 0,
    start: Optional[str] = None,
    end: Optional[str] = None,
    admin_user_id: str = Depends(require_admin),
):
    """Recent pipeline run history - what the admin dashboard's run log renders.
    Paginated (limit/offset) and optionally date-filtered (start/end, ISO timestamps)
    so the list doesn't have to render every run at once."""
    return get_recent_pipeline_runs(limit=limit, offset=offset, since=start, until=end)


@router.get("/langsmith/summary")
def langsmith_summary(admin_user_id: str = Depends(require_admin)):
    """Cost/latency/error summary over the last 24h of traced LLM calls - operational
    cost/latency/error only. Model QUALITY metrics (groundedness, relevance,
    advice-avoidance, classification precision/recall) live in the Evaluation section
    instead, backed by eval_runs - see the /eval/runs routes below."""
    return get_langsmith_summary()


@router.get("/eval/runs")
def list_eval_runs(eval_type: Optional[str] = None, admin_user_id: str = Depends(require_admin)):
    """Recent eval run history - what the admin page's Evaluation section renders.
    Populated by every eval type below, all triggerable from here: eval/run_generation_eval.py,
    eval/run_insight_eval.py, eval/score_guardrails.py, eval/score_research_order.py,
    eval/run_live_sample_eval.py, and eval/score_classification.py - the last of which
    still needs a human labeling pass at least once (see eval/export_labels.py) before
    its own trigger route can re-score anything."""
    return get_recent_eval_runs(eval_type=eval_type, limit=20)


@router.post("/eval/generation/trigger")
def trigger_generation_eval(admin_user_id: str = Depends(require_admin)):
    """Runs the generation-quality eval (groundedness/relevance/advice-avoidance/
    answer-discovery judged by JUDGE_MODEL) against the default fixture set right now,
    synchronously, and returns the summary - same "blocking for now" posture as
    /pipeline/trigger. Unlike the classification eval, this needs no hand-labeled
    input, so it's safe to trigger on demand. Makes real, live Claude calls for every
    fixture question - not free, not instant, and subject to the same daily token
    quota as normal chat traffic."""
    return run_generation_eval(DEFAULT_GENERATION_EVAL_FIXTURE)["summary"]


@router.post("/eval/insight/trigger")
def trigger_insight_eval(admin_user_id: str = Depends(require_admin)):
    """Runs the insight-synthesis-quality eval (groundedness/relevance/completeness,
    same judges as generation eval) against a fixed set of (ticker, evidence) pairs,
    synthesizing each fresh via synthesize_insight() rather than reading real
    ticker_insights rows - so this eval's result reflects the prompt/model, not
    whatever news happened to exist when it ran (that's what
    /monitoring/quality-samples' "insight" bucket is for). Makes real, live Claude
    calls - not free, not instant."""
    return run_insight_eval()["summary"]


@router.post("/eval/feed-summary/trigger")
def trigger_feed_summary_eval(admin_user_id: str = Depends(require_admin)):
    """Runs the feed-summary-quality eval (groundedness/completeness, same judges as
    generation/insight eval) against a fixed set of (article, feed) pairs, using the
    exact same summarize_for_feed() function the live pipeline calls for both custom
    and common feed items. Makes real, live Claude calls - not free, not instant."""
    return run_feed_summary_eval()["summary"]


@router.post("/eval/guardrails/trigger")
def trigger_guardrail_eval(admin_user_id: str = Depends(require_admin)):
    """Runs per-layer TP/FP scoring for both guardrails (regex + LLM layer,
    independently) against the hand-labeled adversarial+quality test sets right now,
    synchronously, and returns the summary. Small, fixed-size fixture sets (see
    agent/eval/fixtures/*_guardrail_test_set.json) - grow these over time the same way
    agent/eval/export_labels.py's classification worksheet grows, especially with real
    production near-misses once there's traffic. Makes real, live Groq calls for the
    LLM-layer half of the scoring."""
    return run_guardrail_eval(DEFAULT_INPUT_GUARDRAIL_FIXTURE, DEFAULT_OUTPUT_GUARDRAIL_FIXTURE)


@router.post("/eval/classification/trigger")
def trigger_classification_eval(admin_user_id: str = Depends(require_admin)):
    """Re-scores the classification eval (precision/recall/false-skip-rate + a full
    ROC curve/AUC) against the most recently hand-labeled worksheet
    (agent/eval/labeling_worksheet_filled.csv by convention - see export_labels.py)
    right now, synchronously, and returns the summary. Needs no NEW human labeling to
    re-run - safe to trigger repeatedly after changing common_feed_templates.match_threshold
    or the classifier's embedding/prompt, as long as that file's correct_feed ground
    truth is still valid. 404s if the file doesn't exist yet - a first labeling pass
    (export_labels.py, then a human filling in correct_feed) is still required once,
    same reason this is the one eval type with no "first run" button."""
    if not os.path.exists(DEFAULT_LABELS_PATH):
        raise HTTPException(
            status_code=404,
            detail=(
                f"No labeled worksheet found at {DEFAULT_LABELS_PATH}. Run "
                "`python -m agent.eval.export_labels`, fill in the correct_feed column, "
                "save it at that path, then try again."
            ),
        )
    return run_classification_eval(DEFAULT_LABELS_PATH)


@router.post("/eval/research-order/trigger")
def trigger_research_order_eval(admin_user_id: str = Depends(require_admin)):
    """Runs the research-order guardrail's labeled call-sequence eval (see
    agent/eval/fixtures/research_order_test_set.json) right now, synchronously, and
    returns the summary. The guard itself is deterministic - this is a regression check,
    not judgment against ambiguous input - so it's fast and makes no LLM calls at all."""
    return run_research_order_eval()


@router.post("/eval/live-sample/trigger")
def trigger_live_sample_eval(n: int = 10, hours: int = 24, admin_user_id: str = Depends(require_admin)):
    """Samples up to `n` random completed conduct_analysis requests from the last
    `hours` of REAL traffic and judges each for groundedness/relevance/answer-discovery
    - continuous quality monitoring at a predictable cost, as opposed to
    /eval/generation/trigger's fixed fixture set. `n` defaults to 10/day scale
    deliberately - see eval/run_live_sample_eval.py's own docstring for why judging
    every request live would get expensive fast."""
    return run_live_sample_eval(n=n, hours=hours)["summary"]


@router.get("/efficiency/summary")
def efficiency_summary(hours: int = 24 * 7, admin_user_id: str = Depends(require_admin)):
    """Percentile (p50/p95/max) steps/tokens/latency across recent request_trace rows,
    plus the recursion-limit hit rate - what the admin page's Efficiency subsection
    renders. See db.queries.get_efficiency_summary for why these are percentiles, not
    just the single average LangSmith's summary above already gives."""
    return get_efficiency_summary(hours=hours)


@router.get("/alerts/recent")
def recent_alerts(admin_user_id: str = Depends(require_admin)):
    """Recent ops_alerts rows (cost/latency/step-count threshold trips), newest first -
    what the admin page's Alerts subsection renders. No question/answer content in
    these rows at all - see ops_alerts in schema.sql."""
    return get_recent_ops_alerts()


def _metric_window(hours: int, start: Optional[str], end: Optional[str]) -> tuple[datetime, datetime, str, str]:
    if start or end:
        if not start or not end:
            raise HTTPException(status_code=422, detail="start and end are required together.")
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="start and end must be valid ISO timestamps.") from exc
        if start_dt.tzinfo is None or end_dt.tzinfo is None or end_dt <= start_dt:
            raise HTTPException(status_code=422, detail="end must be after start, with timezone information.")
    else:
        if hours <= 0:
            raise HTTPException(status_code=422, detail="hours must be greater than zero.")
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(hours=hours)
    return start_dt, end_dt, start_dt.isoformat(), end_dt.isoformat()


@router.get("/metrics/summary")
def metrics_summary(
    hours: int = 24,
    start: Optional[str] = None,
    end: Optional[str] = None,
    admin_user_id: str = Depends(require_admin),
):
    """Returns model monitoring, efficiency, and alerts for one shared time window."""
    start_dt, end_dt, since, until = _metric_window(hours, start, end)
    return {
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "monitoring": get_langsmith_summary(start_time=start_dt, end_time=end_dt),
        "efficiency": get_efficiency_summary(since=since, until=until),
        "alerts": get_recent_ops_alerts(since=since, until=until),
    }


@router.post("/monitoring/quality-sampling/trigger")
def trigger_quality_sampling(
    hours: int = QUALITY_SAMPLE_WINDOW_HOURS, admin_user_id: str = Depends(require_admin)
):
    """Runs the continuous quality-sampling monitor (see
    monitoring/quality_sampling.py) right now, synchronously: judges a rate-capped
    sample of recent (within `hours`) custom feed items, common feed items, pipeline
    insights, and chat answers for groundedness/completeness, and persists one
    quality_samples row per judged item. `hours` is independent of the Monitoring
    section's cost/latency Time window (metrics_summary above) - sampling reads
    directly from each surface's own source table (feed_items, ticker_insights,
    request_trace), not from LangSmith/request_trace aggregates, so it has its own
    window rather than sharing that one. Makes real, live JUDGE_MODEL calls - not free,
    not instant."""
    return run_quality_sampling(hours=hours)


@router.get("/monitoring/quality-samples")
def list_quality_samples(
    surface_type: Optional[str] = None,
    flagged_only: bool = False,
    ticker: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    reviewed: Optional[bool] = None,
    limit: int = 50,
    admin_user_id: str = Depends(require_admin),
):
    """Recent quality_samples rows for the admin page's "Output quality" panel, so a
    specific bad summary/answer can be found and used to drive prompt iteration -
    not just an aggregate score. ticker/start/end/reviewed filter which already-sampled
    rows are shown; independent of the trigger route's `hours`, which controls what gets
    sampled in the first place."""
    return get_quality_samples(
        surface_type=surface_type,
        flagged_only=flagged_only,
        ticker=ticker,
        since=start,
        until=end,
        reviewed=reviewed,
        limit=limit,
    )


@router.post("/monitoring/quality-samples/{sample_id}/review")
def review_quality_sample(sample_id: str, admin_user_id: str = Depends(require_admin)):
    """Marks a flagged quality_samples row as reviewed by the current admin."""
    return mark_quality_sample_reviewed(sample_id, admin_user_id)


@router.post("/monitoring/guardrail-sampling/trigger")
def trigger_guardrail_sampling(
    hours: int = QUALITY_SAMPLE_WINDOW_HOURS, admin_user_id: str = Depends(require_admin)
):
    """Runs the continuous guardrail-monitoring sampler (see
    monitoring/guardrail_sampling.py) right now, synchronously: re-checks a rate-capped
    sample of recent questions (input guardrail) and recent passed answers (output
    guardrail) against both the live regex/LLM layers and an independent evaluation-tier
    judge, and persists one guardrail_samples row per judged item. Makes real, live LLM
    calls - not free, not instant."""
    return run_guardrail_sampling(hours=hours)


@router.get("/monitoring/guardrail-samples")
def list_guardrail_samples(
    guardrail_type: Optional[str] = None,
    flagged_only: bool = False,
    ticker: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    reviewed: Optional[bool] = None,
    limit: int = 50,
    admin_user_id: str = Depends(require_admin),
):
    """Recent guardrail_samples rows for the admin page's "Guardrail monitoring" panel."""
    return get_guardrail_samples(
        guardrail_type=guardrail_type,
        flagged_only=flagged_only,
        ticker=ticker,
        since=start,
        until=end,
        reviewed=reviewed,
        limit=limit,
    )


@router.post("/monitoring/guardrail-samples/{sample_id}/review")
def review_guardrail_sample(sample_id: str, admin_user_id: str = Depends(require_admin)):
    """Marks a flagged guardrail_samples row as reviewed by the current admin."""
    return mark_guardrail_sample_reviewed(sample_id, admin_user_id)


@router.post("/monitoring/classification-sampling/trigger")
def trigger_classification_sampling(
    hours: int = QUALITY_SAMPLE_WINDOW_HOURS, admin_user_id: str = Depends(require_admin)
):
    """Runs the continuous feed-classification monitoring sampler (see
    monitoring/classification_sampling.py) right now, synchronously: judges a rate-capped
    sample of recent custom/common feed classifications with an independent evaluation
    judge, and persists one classification_samples row per judged item. Makes real,
    live LLM calls - not free, not instant."""
    return run_classification_sampling(hours=hours)


@router.get("/monitoring/classification-samples")
def list_classification_samples(
    classification_type: Optional[str] = None,
    flagged_only: bool = False,
    ticker: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    reviewed: Optional[bool] = None,
    limit: int = 50,
    admin_user_id: str = Depends(require_admin),
):
    """Recent classification_samples rows for the admin page's unified monitoring panel."""
    return get_classification_samples(
        classification_type=classification_type,
        flagged_only=flagged_only,
        ticker=ticker,
        since=start,
        until=end,
        reviewed=reviewed,
        limit=limit,
    )


@router.post("/monitoring/classification-samples/{sample_id}/review")
def review_classification_sample(sample_id: str, admin_user_id: str = Depends(require_admin)):
    """Marks a flagged classification_samples row as reviewed by the current admin."""
    return mark_classification_sample_reviewed(sample_id, admin_user_id)


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
