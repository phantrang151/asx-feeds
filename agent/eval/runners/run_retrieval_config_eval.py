"""
Compares retrieval configurations end to end for chat_answer: does better retrieval recall give
more complete answers, or does extra evidence bring more unsupported claims?

Only retrieval varies - the answer model, synthesis prompt and judges are production's own:
  retrieval   semantic  = production match_ticker_news RPC (embedding cosine, threshold)
              lexical   = the deployed match_ticker_news_lexical RPC (OR of the question's terms)
              hybrid_rrf = reciprocal-rank fusion of the semantic and lexical candidate lists
  answers     agent/shared/synthesize.py::synthesize_insight (question set, no ReAct draft)
  judges      agent/eval/judge.py - validated in run_judge_validation_eval.py

Four stages, each writing its own file and reading the previous one, so any stage can be re-run
alone (new judge prompt -> `judge` + `report`; new config -> from `retrieve`):
  retrieve  -> results/retrieval_runs.json        ranked articles + evidence per (question, config)
  generate  -> results/generated_answers.json     one answer per run; runs that retrieved the exact
                                                  same articles share one generation, so differences
                                                  between configs come from evidence, not LLM noise
  judge     -> results/answer_judgements.json     groundedness: claims extracted from the answer, each
                                                    judged against the RETRIEVED evidence;
                                                  completeness: each GOLD fact judged against the answer
                                                    (same reference facts for every config);
                                                  abstention: answer-absent questions should decline
  report    -> results/retrieval_config_comparison.json + .csv (summary) + _per_question.csv
Inputs: fixtures/retrieval_eval_test_set.json (questions, gold articles, gold facts) and
fixtures/retrieval_eval_config.json (configs, threshold, RRF constant, date window).

Stages that call an API save progress per item and resume after an interruption.

Usage:
    python -m agent.eval.runners.run_retrieval_config_eval all
    python -m agent.eval.runners.run_retrieval_config_eval judge
    python -m agent.eval.runners.run_retrieval_config_eval report
"""

import argparse
import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from statistics import mean

from langchain_anthropic import ChatAnthropic

from agent.eval.confusion_matrix import load_fixture
from agent.eval.export_judge_validation_cases import Claims
from agent.eval.judge import judge_answer_found, judge_completeness, judge_groundedness
from agent.eval.judge_validation_compare import fact_covered
from agent.shared.news_text import format_news_content
from agent.shared.synthesize import synthesize_insight
from config import ANALYSIS_MODEL, ANTHROPIC_API_KEY, SUPABASE_DB_URL
from db.queries import match_ticker_news_for_embedding
from tools.embeddings import embed

TEST_SET = "agent/eval/fixtures/retrieval_eval_test_set.json"
CONFIG = "agent/eval/fixtures/retrieval_eval_config.json"
RESULTS = "agent/eval/results"
RUNS = f"{RESULTS}/retrieval_runs.json"
ANSWERS = f"{RESULTS}/generated_answers.json"
JUDGEMENTS = f"{RESULTS}/answer_judgements.json"
COMPARISON = f"{RESULTS}/retrieval_config_comparison.json"
SUMMARY_CSV = f"{RESULTS}/retrieval_config_comparison.csv"
PER_QUESTION_CSV = f"{RESULTS}/retrieval_config_per_question.csv"
EVIDENCE_SOURCE = "search_internal_news_tool"  # same label production evidence carries
MAX_WORKERS = 4

LEXICAL_SQL = """
with q as (select replace(plainto_tsquery('english', %(question)s)::text, ' & ', ' | ') as terms)
select l.id::text, n.title, n.snippet, n.publisher, n.source_url, l.lexical_score
from q, match_ticker_news_lexical(q.terms, %(tickers)s, %(pool)s) l
join ticker_news n on n.id = l.id
where n.published_at >= %(since)s
order by l.lexical_score desc, l.id
"""


# ---------------------------------------------------------------- retrieval

def _evidence(row: dict) -> dict:
    """Exactly what search_internal_news_tool hands to synthesis (see tools/react_tools.py)."""
    return {"source": EVIDENCE_SOURCE,
            "content": f"{format_news_content(row['title'], row.get('snippet'))} ({row.get('publisher') or 'Unknown'})",
            "url": row.get("source_url")}


def semantic_candidates(ticker: str, question: str, cfg: dict, since: str) -> list[dict]:
    rows = match_ticker_news_for_embedding([ticker], embed(question), match_count=cfg["candidate_pool"],
                                           similarity_threshold=cfg["semantic_threshold"], news_since=since)
    return [{**r, "id": str(r["id"]), "semantic_similarity": r["similarity"]} for r in rows]


def lexical_candidates(ticker: str, question: str, cfg: dict, since: str) -> list[dict]:
    import psycopg  # direct connection: the RPC needs the question turned into an OR tsquery first

    with psycopg.connect(SUPABASE_DB_URL) as conn:
        conn.read_only = True
        rows = conn.execute(LEXICAL_SQL, {"question": question, "tickers": [ticker],
                                          "pool": cfg["candidate_pool"], "since": since}).fetchall()
    return [{"id": r[0], "title": r[1], "snippet": r[2], "publisher": r[3], "source_url": r[4],
             "lexical_score": float(r[5])} for r in rows if r[5] > 0]


def rrf_fuse(semantic: list[dict], lexical: list[dict], constant: int) -> list[dict]:
    """Reciprocal-rank fusion: each list contributes 1/(constant + rank) for every article it
    holds. Ties break on the better single rank, then article id, so the order is deterministic."""
    merged, best_rank = {}, {}
    for ranked in (semantic, lexical):
        for rank, row in enumerate(ranked, 1):
            item = merged.setdefault(row["id"], {**row, "rrf_score": 0.0})
            item.update({k: v for k, v in row.items() if v is not None})
            item["rrf_score"] += 1 / (constant + rank)
            best_rank[row["id"]] = min(best_rank.get(row["id"], rank), rank)
    return sorted(merged.values(), key=lambda r: (-r["rrf_score"], best_rank[r["id"]], r["id"]))


def retrieve(question: dict, run_cfg: dict, cfg: dict) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=cfg["news_window_days"])).isoformat()
    sem = semantic_candidates(question["ticker"], question["question"], cfg, since)
    if run_cfg["method"] == "semantic":
        ranked = sem
    elif run_cfg["method"] == "lexical":
        ranked = lexical_candidates(question["ticker"], question["question"], cfg, since)
    elif run_cfg["method"] == "hybrid_rrf":
        ranked = rrf_fuse(sem, lexical_candidates(question["ticker"], question["question"], cfg, since),
                          cfg["rrf_constant"])
    else:
        raise ValueError(f"unknown retrieval method {run_cfg['method']!r}")
    top = ranked[:run_cfg["k"]]
    return {
        "question_id": question["id"], "config": run_cfg["name"], "method": run_cfg["method"], "k": run_cfg["k"],
        "retrieved": [{"article_id": r["id"], "rank": i + 1, "title": r["title"],
                       **{s: r[s] for s in ("semantic_similarity", "lexical_score", "rrf_score") if s in r}}
                      for i, r in enumerate(top)],
        "evidence": [_evidence(r) for r in top],
    }


# ---------------------------------------------------------------- generation / judging

def generation_key(run: dict) -> str:
    """Runs of one question that retrieved the same articles in the same order get the same
    evidence, so they share a single generated answer."""
    return f"{run['question_id']}|{','.join(r['article_id'] for r in run['retrieved'])}"


def _claim_extractor():
    return ChatAnthropic(model=ANALYSIS_MODEL, api_key=ANTHROPIC_API_KEY).with_structured_output(Claims)


def judge_answer(question: dict, run: dict, answer: str) -> dict:
    """All judge calls for one answer. Judges see only the answer, the retrieved evidence, the
    question and the gold fact texts - never the gold article ids or any metric."""
    evidence = run["evidence"]
    claims = _claim_extractor().invoke(f"Split this answer into atomic statements:\n\n{answer}").claims

    def claim_call(claim: str) -> dict:
        g = judge_groundedness(claim, evidence)
        return {"claim": claim, "supported": g.grounded, "judge_output": g.model_dump()}

    def fact_call(fact: str) -> dict:
        c = judge_completeness(question["question"], answer, [{"source": "gold_fact", "content": fact}])
        return {"fact": fact, "covered": fact_covered(c.model_dump()), "judge_output": c.model_dump()}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        claim_results = list(pool.map(claim_call, claims))
        fact_results = list(pool.map(fact_call, question["gold_facts"]))
    whole = judge_groundedness(answer, evidence)
    result = {
        "question_id": question["id"], "config": run["config"],
        "claims": claim_results, "facts": fact_results,
        "whole_answer_groundedness": whole.model_dump(), "abstention": None,
    }
    if not question["answerable"]:
        a = judge_answer_found(question["question"], answer)
        result["abstention"] = {"declined": not a.found_answer, "judge_output": a.model_dump()}
    return result


def _resumable(items: list, key, work, out_path: str) -> list:
    """Runs `work` over items, saving each result to <out_path>.progress so an interrupted stage
    resumes where it stopped. Returns results in item order and writes out_path."""
    progress = out_path + ".progress"
    done = {key(r): r for r in load_fixture(progress)} if os.path.exists(progress) else {}
    todo = [i for i in items if key(i) not in done]
    print(f"  {len(todo)} to do, {len(done)} reused from an interrupted run")
    for item in todo:
        result = work(item)
        done[key(item)] = result
        _write_json(progress, list(done.values()))
    results = [done[key(i)] for i in items]
    _write_json(out_path, results)
    os.remove(progress)
    return results


def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- report (pure)

def _ratio(num, den):
    return round(num / den, 4) if den else None


def _avg(values):
    values = [v for v in values if v is not None]
    return round(mean(values), 4) if values else None


def per_question_rows(test_set: list[dict], runs: list[dict], answers: list[dict], judgements: list[dict]) -> list[dict]:
    q = {x["id"]: x for x in test_set}
    ans = {(a["question_id"], a["config"]): a for a in answers}
    jud = {(j["question_id"], j["config"]): j for j in judgements}
    rows = []
    for run in runs:
        key = (run["question_id"], run["config"])
        question, a, j = q[run["question_id"]], ans[key], jud[key]
        gold, got = set(question["gold_article_ids"]), [r["article_id"] for r in run["retrieved"]]
        hits = len(gold & set(got))
        n_claims = len(j["claims"])
        rows.append({
            "question_id": run["question_id"], "config": run["config"], "answerable": question["answerable"],
            "n_retrieved": len(got), "gold_retrieved": hits,
            "recall": _ratio(hits, len(gold)), "precision": _ratio(hits, len(got)) if gold else None,
            "n_claims": n_claims, "unsupported_claims": sum(not c["supported"] for c in j["claims"]),
            "groundedness": _ratio(sum(c["supported"] for c in j["claims"]), n_claims),
            "whole_answer_groundedness": j["whole_answer_groundedness"]["groundedness_pct"] / 100,
            "completeness": _ratio(sum(f["covered"] for f in j["facts"]), len(j["facts"])),
            "declined": j["abstention"]["declined"] if j["abstention"] else None,
            "answer_shared_with": a.get("shared_with") or "",
        })
    return rows


def summarize(rows: list[dict]) -> list[dict]:
    out = []
    for config in dict.fromkeys(r["config"] for r in rows):
        rs = [r for r in rows if r["config"] == config]
        answerable = [r for r in rs if r["answerable"]]
        absent = [r for r in rs if not r["answerable"]]
        out.append({
            "config": config,
            "recall": _avg(r["recall"] for r in answerable),
            "precision": _avg(r["precision"] for r in answerable),
            "avg_articles_retrieved": _avg(r["n_retrieved"] for r in rs),
            "groundedness": _avg(r["groundedness"] for r in rs),
            "whole_answer_groundedness": _avg(r["whole_answer_groundedness"] for r in rs),
            "unsupported_claims_total": sum(r["unsupported_claims"] for r in rs),
            "completeness": _avg(r["completeness"] for r in answerable),
            "abstention_correct": f"{sum(bool(r['declined']) for r in absent)}/{len(absent)}",
        })
    return out


# ---------------------------------------------------------------- stages

def stage_retrieve(test_set, cfg):
    print("Stage 1: retrieve")
    items = [(q, c) for q in test_set for c in cfg["configs"]]
    runs = [retrieve(q, c, cfg) for q, c in items]  # no LLM calls - quick and free to redo
    _write_json(RUNS, runs)
    return runs


def stage_generate(test_set, runs):
    print("Stage 2: generate")
    q = {x["id"]: x for x in test_set}
    first_run = {}
    for run in runs:
        first_run.setdefault(generation_key(run), run)
    unique = list(first_run.values())
    print(f"  {len(runs)} runs -> {len(unique)} unique evidence sets to generate")
    generated = _resumable(
        unique, generation_key,
        lambda run: {"key": generation_key(run), "answer": synthesize_insight(
            q[run["question_id"]]["ticker"], run["evidence"], question=q[run["question_id"]]["question"])},
        ANSWERS + ".generations")
    by_key = {g["key"]: g["answer"] for g in generated}
    answers = []
    for run in runs:
        owner = first_run[generation_key(run)]
        answers.append({"question_id": run["question_id"], "config": run["config"],
                        "answer": by_key[generation_key(run)],
                        "shared_with": owner["config"] if owner is not run else None})
    _write_json(ANSWERS, answers)
    os.remove(ANSWERS + ".generations")
    return answers


def stage_judge(test_set, runs, answers):
    print("Stage 3: judge")
    q = {x["id"]: x for x in test_set}
    ans = {(a["question_id"], a["config"]): a["answer"] for a in answers}
    return _resumable(
        runs, lambda r: f"{r['question_id']}|{r['config']}",
        lambda run: judge_answer(q[run["question_id"]], run, ans[(run["question_id"], run["config"])]),
        JUDGEMENTS)


def stage_report(test_set, runs, answers, judgements):
    print("Stage 4: report")
    rows = per_question_rows(test_set, runs, answers, judgements)
    summary = summarize(rows)
    _write_json(COMPARISON, {"summary": summary, "per_question": rows})
    for path, data in ((SUMMARY_CSV, summary), (PER_QUESTION_CSV, rows)):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)
    print(f"{'config':<14}{'recall':>8}{'ground.':>9}{'whole':>8}{'unsup':>7}{'complete':>10}{'abstain':>9}")
    for s in summary:
        print(f"{s['config']:<14}{s['recall']:>8}{s['groundedness']:>9}{s['whole_answer_groundedness']:>8}"
              f"{s['unsupported_claims_total']:>7}{s['completeness']:>10}{s['abstention_correct']:>9}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["retrieve", "generate", "judge", "report", "all"])
    parser.add_argument("--test-set", default=TEST_SET)
    parser.add_argument("--config", default=CONFIG)
    args = parser.parse_args()

    test_set, cfg = load_fixture(args.test_set), load_fixture(args.config)
    runs = stage_retrieve(test_set, cfg) if args.stage in ("retrieve", "all") else load_fixture(RUNS)
    if args.stage == "retrieve":
        raise SystemExit
    answers = stage_generate(test_set, runs) if args.stage in ("generate", "all") else load_fixture(ANSWERS)
    if args.stage == "generate":
        raise SystemExit
    judgements = stage_judge(test_set, runs, answers) if args.stage in ("judge", "all") else load_fixture(JUDGEMENTS)
    stage_report(test_set, runs, answers, judgements)
