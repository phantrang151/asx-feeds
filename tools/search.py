import yfinance as yf
from yfinance.exceptions import YFRateLimitError, YFException
from requests.exceptions import HTTPError
from requests.exceptions import ConnectionError
from requests.exceptions import Timeout
from tools.logger import get_logger

logger = get_logger(__name__)

class NewsRateLimitError(Exception):
    """Raised when the news provider rate limits requests."""
    pass

def search_news(ticker: str, max_results: int = 20) -> list[dict] | None:
    """Get recent news headlines for an ASX ticker using yfinance."""
    if not ticker:
        logger.warning("No ticker provided for news search.")
        return None

    try:
        stock = yf.Ticker(ticker)
        news_items = stock.news or None

        if not news_items:
            logger.info(f"No news found for ticker: {ticker}")
            return []

        articles = []
        for item in news_items[:max_results]:
            # yfinance has changed its news response shape across versions -
            # handle both the nested "content" structure and the flat structure
            content = item.get("content", item)

            title = content.get("title", None)

            provider = content.get("provider")
            if isinstance(provider, dict):
                publisher = provider.get("displayName", "")
            else:
                publisher = content.get("publisher", "")

            canonical_url = content.get("canonicalUrl")
            if isinstance(canonical_url, dict):
                link = canonical_url.get("url") or None
            else:
                link = content.get("link") or None

            published = content.get("pubDate") or content.get("providerPublishTime", "")

            # yfinance's own editorial dek - a real sentence about what the article says,
            # not just the headline. Free (already in the response), unlike the full
            # article body which would need scraping canonicalUrl.
            snippet = content.get("summary") or ""

            if not title or not link:
                logger.warning(f"Skipping news item for ticker {ticker} due to missing title or link: {content}")
                continue
            else:
                articles.append(
                    {
                        "title": title,
                        "publisher": publisher,
                        "link": link,
                        "published": published,
                        "snippet": snippet,
                    }
                )
        if len(articles) == 0:
            logger.error(f"Yahoo contract has changed. No valid news articles found for ticker: {ticker}")
            return None
        else:
            return articles

    except Timeout:
        logger.error(f"Timeout occurred while fetching news for ticker {ticker}.")
        return None

    except HTTPError as e:
        status_code = e.response.status_code if hasattr(e, "response") else 0
        if status_code == 429:
            raise NewsRateLimitError(f"Rate limit exceeded for ticker {ticker}. Please try again later.")
        elif status_code >= 400 and status_code < 500:
            logger.warning(f"Configuration error for ticker {ticker}: {str(e)}")
        elif status_code >= 500:
            raise ConnectionError(f"Yahoo Service not available for ticker {ticker}.")
        else:
            logger.error(f"Unknown HTTP error occurred while fetching news for {ticker}: {str(e)}")
        return None

    except YFRateLimitError as e:
        raise NewsRateLimitError(f"Rate limit exceeded for ticker {ticker}. Please try again later.")

    except YFException as e:
        logger.error(f"Unknown Yahoo error occurred while fetching news for {ticker}: {str(e)}")
        return None
    
    except Exception as e:
        logger.exception(f"Unexpected Exception in search_news for {ticker}: {str(e)}")
        return None

if __name__ == "__main__":
    # Example usage
    ticker = "TLS.AX"  # Replace with your desired ticker
    news_results = search_news(ticker)
    for article in news_results:
        print(article)
