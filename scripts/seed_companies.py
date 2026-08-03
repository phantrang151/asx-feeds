"""
One-off script to seed the `companies` table (real ASX ticker/name pairs) used by the
chat agent's ticker-validation guardrail. Run schema.sql against your Supabase project
first. Safe to re-run - upserts on ticker.

Source: Wikipedia's "S&P/ASX 200" page. The official ASX listed-companies CSV
(asx.com.au/asx/research/ASXListedCompanies.csv) is blocked by an Incapsula WAF from a
server environment, so this only covers the ~200 largest ASX-listed companies rather
than the full ~2000-company exchange. A ticker outside this seed isn't necessarily
fake - see agent/guardrails/tickers.py's live-yfinance fallback for anything not found
here.

Usage:
    python -m scripts.seed_companies
"""

import requests
from bs4 import BeautifulSoup

from db.queries import upsert_companies

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/S%26P/ASX_200"
# Index of the constituents table among every <table> on the page (confirmed by
# inspection - the first two tables are an infobox and an unrelated futures-contract
# table). If Wikipedia's page layout changes, this is the first thing to re-check.
CONSTITUENTS_TABLE_INDEX = 2


def _fetch_constituent_rows() -> list[dict]:
    resp = requests.get(WIKIPEDIA_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find_all("table")[CONSTITUENTS_TABLE_INDEX]

    rows = []
    for tr in table.find_all("tr")[1:]:  # skip header row
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 2:
            continue
        code, company = cells[0], cells[1]
        if not code or not company:
            continue
        rows.append({"ticker": f"{code.upper()}.AX", "company_name": company})
    return rows


def seed_companies():
    rows = _fetch_constituent_rows()
    if not rows:
        raise RuntimeError(
            "No company rows parsed from Wikipedia - the page layout likely changed, "
            "check CONSTITUENTS_TABLE_INDEX and the column order."
        )
    upsert_companies(rows)
    print(f"Upserted {len(rows)} companies.")


if __name__ == "__main__":
    seed_companies()
