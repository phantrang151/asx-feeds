"""
Every user-facing guardrail/decline string in one place, separate from
agent/chat/prompts.py (which holds LLM-facing system prompts, not end-user copy) - so
wording can be found and reviewed without hunting through node code. Draft copy - not
signed off by anyone, expect this to be revised.
"""

TICKER_NOT_FOUND = (
    "I couldn't confirm that ticker against real ASX-listed companies. Please check the "
    "spelling or provide the Yahoo Finance ASX symbol directly (e.g. 'TLS.AX')."
)

ADVICE_SEEKING = (
    "I can help explain what's happening with a stock and why, but I can't tell you "
    "whether to buy, sell, or hold it - that's a personal financial decision. Try "
    "asking a 'why' or 'what happened' question instead."
)

RECURSION_LIMIT_REACHED = (
    "This question needed more research steps than we allow per request. Please try "
    "asking something more specific."
)

TOKEN_CEILING_REACHED = (
    "This question required more processing than we allow per request. Please try "
    "asking something more specific."
)

ADVICE_LANGUAGE_DETECTED = (
    "I generated an answer for this question, but it read too much like investment "
    "advice, so I'm withholding it rather than risk giving you a recommendation. "
    "Please try rephrasing your question to focus on what happened and why."
)
