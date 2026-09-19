def format_news_content(title: str, snippet: "str | None" = None) -> str:
    """Canonical text representation of one news item - the single place every consumer
    (ingestion embeddings, feed-summary prompts, chat tool evidence, eval fixtures,
    quality monitoring) turns a news item into text an embedding or LLM call sees.
    Never use `title` alone downstream of this - a bare headline carries too little
    signal for classification, summarization, or grounded judgment; `snippet` (the
    source's own editorial dek, e.g. yfinance's `summary` field via tools/search.py -
    not full article text) is cheap to include since it's already fetched for free.
    """
    return f"{title} - {snippet}" if snippet else title


def format_feed_content(feed_name: str, feed_description: str) -> str:
    """Canonical text representation of a feed/topic - the single place every consumer
    (description_embedding computation at feed create/update time, decide_feed_sources'
    prompt, summarize_feed_items' prompt) turns a feed into text an embedding or LLM
    call sees. Never embed feed_description alone downstream of this - the name itself
    carries real topical signal (e.g. "Investment in AI" as a phrase) that a
    description-only embedding discards, and two feeds can share very similar
    descriptions while meaning something different because of the name attached.
    """
    return f"{feed_name}: {feed_description}"
