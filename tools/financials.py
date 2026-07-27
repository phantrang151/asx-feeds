from db.queries import get_latest_financial_record


def get_financial_summary(ticker: str) -> str:
    """Returns the most recently stored financial record for a ticker as plain text."""
    record = get_latest_financial_record(ticker)
    if not record:
        return f"No financial records found for {ticker}."
    return (
        f"{ticker} latest financials ({record['period']}): "
        f"revenue={record['revenue']}, profit={record['profit']}, headcount={record['headcount']}"
    )
