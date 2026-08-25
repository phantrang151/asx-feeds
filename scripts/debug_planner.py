import argparse

from agent.pipelines.insight_graph import synthesize_insight_for
from db.queries import get_all_watchlist_entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the insight planner for one ticker.")
    parser.add_argument("--ticker", required=True, help="ASX ticker, for example NAB.AX")
    parser.add_argument("--user-id", help="Run for one specific watchlist user")
    args = parser.parse_args()

    ticker = args.ticker.strip().upper()
    user_ids = [args.user_id] if args.user_id else sorted({
        entry["user_id"]
        for entry in get_all_watchlist_entries()
        if entry["ticker"] == ticker
    })

    if not user_ids:
        raise SystemExit(f"No users are watching {ticker}.")

    for user_id in user_ids:
        print(f"Running planner for {ticker}, user {user_id}...")
        synthesize_insight_for(user_id, ticker)
        print(f"Completed planner for {ticker}, user {user_id}.")


if __name__ == "__main__":
    main()
