from unittest.mock import patch

from agent.pipelines.insight_nodes import synthesize_node


def _state(**overrides):
    state = {
        "user_id": "user-1",
        "ticker": "NAB.AX",
        "items_by_feed": {"AI Investment": [{"id": "item-1"}], "Revenue Trend": []},
        "feed_ids": {"AI Investment": "f-ai", "Revenue Trend": "f-rev"},
        "step_results": [{"step": "AI Investment", "items": [{"id": "item-1"}], "summary": "s", "sufficient": True}],
    }
    return {**state, **overrides}


def _run(state):
    with patch("agent.pipelines.insight_nodes.synthesize_insight", return_value="insight"), \
         patch("agent.pipelines.insight_nodes.check_output", return_value=(True, [], "")), \
         patch("agent.pipelines.insight_nodes.insert_ticker_insight") as insert:
        synthesize_node(state)
    return insert.call_args.args[4]  # feed_summaries


def test_every_feed_summary_carries_its_feed_id():
    summaries = _run(_state())
    assert {s["feed_name"]: s["feed_id"] for s in summaries} == {"AI Investment": "f-ai", "Revenue Trend": "f-rev"}


def test_state_without_feed_ids_still_synthesizes():
    state = _state()
    del state["feed_ids"]
    assert all(s["feed_id"] is None for s in _run(state))
