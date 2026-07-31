import yfinance as yf


def search_news(ticker: str, max_results: int = 5) -> list[dict]:
    """Get recent news headlines for an ASX ticker using yfinance."""
    if not ticker:
        return []

    try:
        stock = yf.Ticker(ticker)
        news_items = stock.news or []

        if not news_items:
            return []

        articles = []
        for item in news_items[:max_results]:
            # yfinance has changed its news response shape across versions -
            # handle both the nested "content" structure and the flat structure
            content = item.get("content", item)

            title = content.get("title", "No title")

            provider = content.get("provider")
            if isinstance(provider, dict):
                publisher = provider.get("displayName", "Unknown")
            else:
                publisher = content.get("publisher", "Unknown")

            canonical_url = content.get("canonicalUrl")
            if isinstance(canonical_url, dict):
                link = canonical_url.get("url") or None
            else:
                link = content.get("link") or None

            published = content.get("pubDate") or content.get("providerPublishTime", "")

            articles.append(
                {
                    "title": title,
                    "publisher": publisher,
                    "link": link,
                    "published": published,
                }
            )

        return articles

    except Exception as e:
        print(f"search_news error for {ticker}: {e}")
        return []
