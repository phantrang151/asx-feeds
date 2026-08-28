"""Regression gate (catalog case I8): the research-order guard is deterministic and the
fixture replay makes no LLM/DB calls, so this runs on every push like a unit test even
though it's scoring a labeled fixture set. Reuses the real guard functions via
score_research_order - never reimplements the state machine, so this test and the live
guard can't drift apart. persist=False so running this in CI never writes to eval_runs."""

from agent.eval.confusion_matrix import load_fixture
from agent.eval.score_research_order import score_research_order, DEFAULT_FIXTURE


def test_research_order_guard_matches_every_labeled_scenario():
    rows = load_fixture(DEFAULT_FIXTURE)
    result = score_research_order(rows)

    assert result["fp"] == 0
    assert result["fn"] == 0
    assert result["true_positive_rate"] == 1.0
    assert result["false_positive_rate"] == 0.0
