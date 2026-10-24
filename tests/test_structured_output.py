"""Tests for agent/shared/structured_output.py's invoke_structured_with_repair: parse, repair the
malformed shapes Claude has returned, retry with a fresh call, then raise StructuredOutputError.
No LLM needed - the structured LLM is a fake returning include_raw=True style results."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from agent.shared.structured_output import StructuredOutputError, invoke_structured_with_repair


class Judgment(BaseModel):
    is_advice: bool
    reasoning: str


def _ok(obj):
    return {"parsed": obj, "parsing_error": None, "raw": AIMessage(content="")}


def _bad(args):
    raw = AIMessage(content="", tool_calls=[{"name": "Judgment", "args": args, "id": "t1"}])
    return {"parsed": None, "parsing_error": ValueError("did not validate"), "raw": raw}


def _llm(*results):
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.side_effect = list(results)
    return llm, llm.with_structured_output.return_value


def test_valid_output_is_returned_as_is():
    good = Judgment(is_advice=False, reasoning="explains only")
    llm, structured = _llm(_ok(good))
    assert invoke_structured_with_repair(llm, Judgment, "p") is good
    assert structured.invoke.call_count == 1


@pytest.mark.parametrize("args", [
    {"parameter": {"is_advice": False, "reasoning": "r"}},                 # nested under a placeholder key
    {"parameter": '{"is_advice": false, "reasoning": "r"}'},                # whole payload as a JSON string
    {"is_advice": False, "reasoning": "r", "extra": '{"is_advice": false, "reasoning": "r"}'},
])
def test_malformed_shapes_are_repaired_without_a_second_call(args):
    llm, structured = _llm(_bad(args))
    result = invoke_structured_with_repair(llm, Judgment, "p")
    assert result == Judgment(is_advice=False, reasoning="r")
    assert structured.invoke.call_count == 1


def test_unrepairable_output_is_retried_with_a_fresh_call():
    good = Judgment(is_advice=True, reasoning="recommends buying")
    llm, structured = _llm(_bad({"garbage": 1}), _ok(good))
    assert invoke_structured_with_repair(llm, Judgment, "p") is good
    assert structured.invoke.call_count == 2


def test_gives_up_with_structured_output_error_carrying_the_raw_args(caplog):
    llm, structured = _llm(_bad({"garbage": 1}), _bad({"garbage": 2}))
    with pytest.raises(StructuredOutputError) as exc:
        invoke_structured_with_repair(llm, Judgment, "p")
    assert exc.value.schema_name == "Judgment"
    assert exc.value.raw_args == {"garbage": 2} and exc.value.attempts == 2
    assert caplog.text.count("Unparseable Judgment output") == 2   # each failed attempt is logged


def test_config_reaches_every_attempt():
    # So the token-budget callback and RequestTracer see the retry too, not just the first call.
    config = {"callbacks": ["cb"], "metadata": {"step_name": "router"}}
    llm, structured = _llm(_bad({"garbage": 1}), _ok(Judgment(is_advice=False, reasoning="r")))
    invoke_structured_with_repair(llm, Judgment, "p", config=config)
    assert all(c.kwargs["config"] is config for c in structured.invoke.call_args_list)
