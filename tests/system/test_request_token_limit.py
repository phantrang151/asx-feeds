from unittest.mock import patch, MagicMock
import pytest
from config import TOKEN_CEILING_PER_REQUEST
from agent.guardrails.token_budget import TokenBudgetCallback, TokenBudgetExceededError, total_tokens_from


"""
Level 1: test inside the token_budget.py
"""
def test_request_token_limit():
    call_back_instance = TokenBudgetCallback(ceiling=TOKEN_CEILING_PER_REQUEST)
    
    with patch('agent.guardrails.token_budget.total_tokens_from', return_value=TOKEN_CEILING_PER_REQUEST + 1):
        with pytest.raises(TokenBudgetExceededError) as excinfo:
            call_back_instance.on_llm_end(MagicMock())
            
    assert (f"Token budget exceeded: {call_back_instance.total_tokens} > {TOKEN_CEILING_PER_REQUEST}" in str(excinfo.value))

"""
Level 2: test inside the analysis_node.py
"""
# conduct_analysis_node catches TokenBudgetExceededError / GraphRecursionError and returns a
# Command that declines politely - so these tests assert on what the node RETURNS, not on a
# raised exception. Only DailyTokenBudgetExceededError is meant to escape (-> 429 in main.py).
#
# The ReAct agent is replaced by a fake whose invoke() raises, so no LLM call is made.
# Marked slow: importing agent.chat.analysis_node opens the Postgres memory store at import
# time (_store = get_store()), ~20 s and needs the database. The import is done inside the
# helper, not at the top of this file, so the Level 1 test above stays fast.


def _run_node_with_agent_raising(exc, synthesis_raises=None):
    """Runs conduct_analysis_node with a fake ReAct agent. `exc` is raised by the agent's
    invoke(); with exc=None the agent succeeds and `synthesis_raises` is raised by the final
    synthesis step instead. Returns (node result, the synthesize_insight mock)."""
    from langchain_core.messages import AIMessage, HumanMessage

    from agent.chat import analysis_node

    fake_agent = MagicMock()
    if exc is not None:
        fake_agent.invoke.side_effect = exc
    else:
        fake_agent.invoke.return_value = {"messages": [AIMessage(content="draft answer")]}
    state = {"ticker": "ANZ.AX", "messages": [HumanMessage(content="What was ANZ's FY2025 profit?")]}
    config = {"configurable": {"langgraph_user_id": "user-1"}}

    with patch.object(analysis_node, "_make_react_agent", return_value=fake_agent), \
         patch.object(analysis_node, "synthesize_insight", side_effect=synthesis_raises) as synth:
        result = analysis_node.conduct_analysis_node(state, config)
    return result, synth


@pytest.mark.slow
def test_token_ceiling_in_react_loop_becomes_a_polite_decline():
    from agent.chat import decline_messages

    command, synth = _run_node_with_agent_raising(TokenBudgetExceededError(21000, 20000))

    update = command.update
    assert update["category"] == "declined"
    assert update["result"] == decline_messages.TOKEN_CEILING_REACHED
    assert update["messages"][-1].content == decline_messages.TOKEN_CEILING_REACHED  # what the user sees
    assert update["evidence"] == [] and update["references"] == []
    synth.assert_not_called()  # no half-built answer after an abort


@pytest.mark.slow
def test_token_ceiling_during_synthesis_is_also_declined():
    # The ceiling covers the whole request: synthesis runs inside the same try block.
    from agent.chat import decline_messages

    command, synth = _run_node_with_agent_raising(None, synthesis_raises=TokenBudgetExceededError(21000, 20000))

    synth.assert_called_once()
    assert command.update["category"] == "declined"
    assert command.update["result"] == decline_messages.TOKEN_CEILING_REACHED


@pytest.mark.slow
def test_recursion_limit_gets_its_own_decline_message():
    from langgraph.errors import GraphRecursionError

    from agent.chat import decline_messages

    command, _ = _run_node_with_agent_raising(GraphRecursionError("too many steps"))

    assert command.update["category"] == "declined"
    assert command.update["result"] == decline_messages.RECURSION_LIMIT_REACHED
    assert command.update["result"] != decline_messages.TOKEN_CEILING_REACHED


@pytest.mark.slow
def test_daily_budget_error_is_not_caught_by_the_node():
    # Must escape conduct_analysis_node so main.py's ask_endpoint can turn it into a 429.
    from agent.guardrails.token_budget import DailyTokenBudgetExceededError

    with pytest.raises(DailyTokenBudgetExceededError) as excinfo:
        _run_node_with_agent_raising(DailyTokenBudgetExceededError(200_001, 200_000))

    assert excinfo.value.total_tokens == 200_001
    assert excinfo.value.ceiling == 200_000



"""
Level 3: test at main.py (the /api/ask endpoint)
"""
# What the frontend receives: the per-request ceiling arrives as HTTP 200 with the decline as the
# answer; the daily budget arrives as HTTP 429 with a `detail` message. The graph itself is faked,
# and so is everything ask_endpoint touches outside this process (auth, rate limit, daily budget
# lookup, DB writes, link checking) - patched on api.main, where the endpoint looks them up.
# Marked slow: importing api.main loads the whole app (~60 s, needs the database).


# ask_client fixture: see tests/system/conftest.py (shared with test_llm_connection_errors.py)


def _ask(client):
    return client.post("/api/ask", json={"question": "What was ANZ's FY2025 profit?", "thread_id": "t-1"},
                       headers={"Authorization": "Bearer fake-token"})


@pytest.mark.slow
def test_api_returns_200_with_the_decline_when_request_ceiling_is_hit(ask_client):
    from langchain_core.messages import AIMessage

    from agent.chat import decline_messages

    client, graph, insert_trace = ask_client
    message = decline_messages.TOKEN_CEILING_REACHED
    # What conduct_analysis_node's Command leaves in the graph state after the abort.
    graph.invoke.return_value = {"category": "declined", "result": message, "ticker": "ANZ.AX",
                                 "references": [], "messages": [AIMessage(content=message)]}

    resp = _ask(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == message and body["category"] == "declined"
    assert resp.headers["X-Request-ID"]  # every response carries the request id
    trace = insert_trace.call_args.kwargs
    assert trace["status"] == "declined" and trace["decline_reason"] == message
    assert trace["request_id"] == resp.headers["X-Request-ID"]  # the trace row is findable by it


@pytest.mark.slow
def test_api_returns_429_when_daily_budget_is_hit_mid_request(ask_client):
    from agent.guardrails.daily_token_budget import DAILY_BUDGET_MESSAGE
    from agent.guardrails.token_budget import DailyTokenBudgetExceededError

    client, graph, insert_trace = ask_client
    graph.invoke.side_effect = DailyTokenBudgetExceededError(200_001, 200_000)

    resp = _ask(client)

    assert resp.status_code == 429
    assert resp.json()["detail"] == DAILY_BUDGET_MESSAGE  # what AskQuestion.js shows in red
    trace = insert_trace.call_args.kwargs  # the failed request is still traced
    assert trace["status"] == "error" and trace["decline_reason"] == "daily_token_budget_exceeded"


"""
Level 4: test at the frontend (AskQuestion.js)
"""
# JavaScript, so it can't live in this pytest file: see frontend/__tests__/AskQuestion.test.js
# (Jest + React Testing Library; run with `cd frontend && npm test`). It fakes the two responses
# levels 3 checks above - 200 + decline message, 429 + detail - and asserts the decline appears in
# the answer box while the 429 appears as the red error line.
