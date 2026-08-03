"""Pure-logic tests for the keyword layer only - no network/DB. The LLM-judge layer
(llm_judge_advice_check) needs a live GROQ_API_KEY and is exercised by the live smoke
tests instead, not here."""

from agent.guardrails.advice_check import keyword_scan


def test_keyword_scan_clean_analytical_text():
    text = (
        "Profit rose due to cost cuts and headcount reductions, but this may not be "
        "sustainable long-term without organic revenue growth."
    )
    assert keyword_scan(text) == []


def test_keyword_scan_catches_direct_recommendation():
    text = "You should buy this stock given the strong earnings growth."
    assert keyword_scan(text) != []


def test_keyword_scan_catches_good_time_to_buy():
    text = "Given the strong fundamentals, now is a good time to buy."
    assert keyword_scan(text) != []


def test_keyword_scan_does_not_flag_unrelated_buy_sell_mentions():
    # "sold" and "buying" here describe business activity, not investment advice -
    # the keyword layer is deliberately narrow so it doesn't false-positive on this.
    text = "The company sold its logistics arm last quarter as customers kept buying more mobile plans."
    assert keyword_scan(text) == []
