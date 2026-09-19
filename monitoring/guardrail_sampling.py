"""
Continuous production monitoring for the two advice-avoidance guardrails. The live-gate
half of each check reuses the exact same functions the live gates run (same strategy as
agent/eval/runners/run_guardrail_eval.py's fixed-fixture Evaluation panel - one
implementation per layer, not a separately-drifting copy):

- input:  agent/guardrails/advice_check.py::keyword_scan_advice_seeking (regex) +
          agent/chat/nodes.py::classify_request (the live LLM layer, ROUTER_MODEL)
- output: agent/guardrails/advice_check.py::keyword_scan (regex) +
          agent/guardrails/advice_check.py::llm_judge_advice_check (the live LLM layer,
          already JUDGE_MODEL-tier)

Each sample also gets an independent "evaluation" verdict from agent/eval/judge.py -
a separately-implemented judge the live gate never calls, so this is never just the live
gate grading its own homework a second time:

- input:  eval_judge_advice_seeking - a genuinely stronger tier than the live input
          gate's own LLM layer, since that one never rises above ROUTER_MODEL.
- output: eval_judge_advice_check - same JUDGE_MODEL tier as the live output gate (that's
          already the strongest tier this app uses anywhere, so there's no stronger tier
          left to reach for), but still its own prompt/implementation rather than a
          re-run of llm_judge_advice_check itself. See eval_judge_advice_check's own
          docstring for exactly what that does and doesn't buy you.

A sample is flagged when the evaluation verdict disagrees with what the live gate
actually decided for that request - the actionable "this may have been misclassified"
signal.

Output-guardrail sampling can only audit PASSED requests: a blocked response's text is
never persisted (request_trace.answer is only set on status='completed'), by design, so
this catches false negatives (missed violations), not false positives.
"""

import logging
import math
import random

from langchain_core.messages import HumanMessage

from config import QUALITY_SAMPLE_RATE, QUALITY_SAMPLE_CAP, QUALITY_SAMPLE_WINDOW_HOURS
from db.queries import (
    get_recent_request_traces_for_input_guardrail_sampling,
    get_eligible_request_traces_for_sampling,
    get_sampled_guardrail_source_ids,
    insert_guardrail_samples,
)
from agent.guardrails.advice_check import keyword_scan, keyword_scan_advice_seeking
from agent.chat.nodes import classify_request
from agent.eval.judge import eval_judge_advice_seeking, eval_judge_advice_check

logger = logging.getLogger(__name__)


def _sample_size(eligible_n: int, rate: float = QUALITY_SAMPLE_RATE, cap: int = QUALITY_SAMPLE_CAP) -> int:
    """Same rate-with-a-ceiling sizing as monitoring/quality_sampling.py, so guardrail
    sampling cost is just as predictable regardless of traffic volume."""
    if eligible_n <= 0:
        return 0
    return min(cap, eligible_n, math.ceil(rate * eligible_n))


def _select_candidates(candidates: list[dict], guardrail_type: str) -> list[dict]:
    """Excludes already-sampled request_trace rows BEFORE spending a judge call, then
    randomly picks _sample_size(...) of what's left."""
    already_sampled = get_sampled_guardrail_source_ids(guardrail_type, [c["id"] for c in candidates])
    fresh = [c for c in candidates if c["id"] not in already_sampled]
    return random.sample(fresh, _sample_size(len(fresh)))


def sample_input_guardrail(hours: int = QUALITY_SAMPLE_WINDOW_HOURS) -> dict:
    """Re-checks a rate-capped sample of recent questions with BOTH live-gate layers run
    fresh: the regex layer (keyword_scan_advice_seeking) and the live LLM layer
    (classify_request, ROUTER_MODEL) - re-run rather than read from the historical
    request_trace row, since that field is null whenever a bypass path skipped the
    router entirely (e.g. a known-shape latest-news lookup), which would otherwise leave
    column 2 empty for a lot of real traffic. Then judges each independently with
    eval_judge_advice_seeking (JUDGE_MODEL) - see this module's docstring for why that's a
    genuinely new check, not a duplicate of the live gate's own (cheaper) LLM layer."""
    chosen = _select_candidates(get_recent_request_traces_for_input_guardrail_sampling(hours), "input")

    rows = []
    for row in chosen:
        question = row["question"]
        try:
            regex_flagged = bool(keyword_scan_advice_seeking(question))
            router_result = classify_request([HumanMessage(content=question)])
            evaluation = eval_judge_advice_seeking(question)
        except Exception:
            logger.warning("guardrail_sampling: judge call failed for input source_id=%s", row["id"], exc_info=True)
            continue

        llm_flagged = router_result.is_advice_seeking
        live_verdict = llm_flagged if not regex_flagged else True

        rows.append({
            "guardrail_type": "input",
            "source_id": row["id"],
            "ticker": row.get("ticker"),
            "text": question,
            "regex_flagged": regex_flagged,
            "llm_flagged": llm_flagged,
            "eval_flagged": evaluation.is_advice_seeking,
            "eval_reasoning": evaluation.reasoning,
            "flagged": evaluation.is_advice_seeking != live_verdict,
        })

    inserted = insert_guardrail_samples(rows)
    return {"n_sampled": len(inserted), "n_flagged": sum(1 for r in inserted if r["flagged"])}


def sample_output_guardrail(hours: int = QUALITY_SAMPLE_WINDOW_HOURS) -> dict:
    """Same as sample_input_guardrail above, for completed (passed) chat answers only -
    see this module's docstring for why blocked responses can't be sampled at all. Judged
    with eval_judge_advice_check rather than re-running the live gate's own
    llm_judge_advice_check - see this module's docstring and eval_judge_advice_check's own
    docstring for why that still isn't a stronger tier here, just a separate
    implementation."""
    chosen = _select_candidates(get_eligible_request_traces_for_sampling(hours), "output")

    rows = []
    for row in chosen:
        answer = row["answer"]
        try:
            regex_flagged = bool(keyword_scan(answer))
            evaluation = eval_judge_advice_check(answer)
        except Exception:
            logger.warning("guardrail_sampling: judge call failed for output source_id=%s", row["id"], exc_info=True)
            continue

        llm_flagged = row.get("output_guardrail_llm_is_advice")
        live_verdict = llm_flagged if llm_flagged is not None else regex_flagged

        rows.append({
            "guardrail_type": "output",
            "source_id": row["id"],
            "ticker": row.get("ticker"),
            "text": answer,
            "regex_flagged": regex_flagged,
            "llm_flagged": llm_flagged,
            "eval_flagged": evaluation.is_advice,
            "eval_reasoning": evaluation.reasoning,
            "flagged": evaluation.is_advice != live_verdict,
        })

    inserted = insert_guardrail_samples(rows)
    return {"n_sampled": len(inserted), "n_flagged": sum(1 for r in inserted if r["flagged"])}


def run_guardrail_sampling(hours: int = QUALITY_SAMPLE_WINDOW_HOURS) -> dict:
    """Runs both samplers - the one function both the admin trigger route and a future
    scheduled job would call."""
    return {
        "input": sample_input_guardrail(hours),
        "output": sample_output_guardrail(hours),
    }
