import uuid

from agent.chat.persistence import get_store

DEFAULT_ANALYSIS_INSTRUCTIONS = (
    "Always check whether profit or price growth is matched by revenue growth. "
    "If growth appears to come from cost-cutting (e.g. headcount reduction) or price "
    "increases rather than organic revenue growth, flag it explicitly as potentially "
    "unsustainable."
)


def get_procedural_instructions(user_id: str) -> str:
    """
    Procedural memory: HOW the agent should reason, not what happened or what's true.
    Fixed key, exact-match retrieval (store.get, not search) - there's one current rule
    set per user, not a collection of similar-but-different rules to search over.
    """
    store = get_store()
    namespace = (user_id, "procedural")
    result = store.get(namespace, "analysis_instructions")
    if result is None:
        store.put(namespace, "analysis_instructions", {"prompt": DEFAULT_ANALYSIS_INSTRUCTIONS})
        return DEFAULT_ANALYSIS_INSTRUCTIONS
    return result.value["prompt"]


def update_procedural_instructions(user_id: str, new_instructions: str) -> None:
    """
    Call this from a human-in-the-loop feedback step - e.g. the user corrects an insight
    and says 'always check X going forward' - to change HOW future analyses are run.
    Not wired to a UI yet; this is the hook a feedback endpoint would call.
    """
    store = get_store()
    store.put((user_id, "procedural"), "analysis_instructions", {"prompt": new_instructions})


def get_episodic_examples(user_id: str, ticker: str, current_question: str, limit: int = 3) -> str:
    """
    Episodic memory: specific PAST analysis instances for this ticker, retrieved by semantic
    similarity to the current question and used as few-shot examples - not facts, not rules,
    just "here's how a similar question was handled before".
    """
    store = get_store()
    namespace = (user_id, ticker, "episodic")
    results = store.search(namespace, query=current_question, limit=limit)
    if not results:
        return "No previous analyses for this ticker yet."

    formatted = ["Here are some previous analyses for this ticker:"]
    for r in results:
        formatted.append(f"Q: {r.value['question']}\nA: {r.value['insight']}")
    return "\n\n---\n\n".join(formatted)


def store_episodic_example(user_id: str, ticker: str, question: str, insight: str) -> None:
    """
    Writes a new episodic memory entry after each analysis run, so a future similar
    question retrieves it as an example. This is the 'dynamically updated' half of
    episodic memory - it grows with use rather than being fixed at build time.
    """
    store = get_store()
    namespace = (user_id, ticker, "episodic")
    store.put(namespace, str(uuid.uuid4()), {"question": question, "insight": insight})
