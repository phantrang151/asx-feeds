import yfinance as yf


def get_latest_price(ticker: str) -> str:
    """Returns the latest closing price for an ASX ticker as a plain-text summary."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d")
        if hist.empty:
            return f"No price data found for {ticker}."
        latest = hist.iloc[-1]
        return f"{ticker} latest close: {latest['Close']:.2f} on {hist.index[-1].date()}"
    except Exception as e:
        return f"Error fetching price for {ticker}: {e}"
