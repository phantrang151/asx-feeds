from concurrent.futures import ThreadPoolExecutor

import requests

from config import CITATION_CHECK_MAX_WORKERS, CITATION_CHECK_TIMEOUT_SECONDS


# tools/search.py's `link` often points at finance.yahoo.com rather than the original
# publisher (yfinance's canonicalUrl syndicates some articles through Yahoo's own
# hosting) - and Yahoo Finance 429s a request with no User-Agent while serving the same
# URL fine (200) with a normal browser one. Confirmed by hand against a real article
# URL. Without this header, every syndicated article looked "unreachable" even though
# a human clicking the link gets the page.
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 401/403 is ambiguous, not dead, on top of the User-Agent fix above: some sites run
# bot protection that blocks any automated client regardless of headers, so a 403 there
# means "blocked our checker", not "link is gone". Treated as reachable so a real,
# working article doesn't get its link stripped; genuinely dead links still surface via
# 404/410/connection errors/timeouts.
_AMBIGUOUS_BLOCKED_STATUSES = (401, 403)


def _is_reachable(url: str) -> bool:
    """Same fail-closed style as tools/price.py/tools/search.py: any exception means
    'not confirmed reachable', never raised. HEAD first (cheaper); falls back to a
    ranged GET for servers that don't support HEAD (405/501) or block it outright."""
    try:
        resp = requests.head(
            url,
            timeout=CITATION_CHECK_TIMEOUT_SECONDS,
            allow_redirects=True,
            headers={"User-Agent": _BROWSER_USER_AGENT},
        )
        if resp.status_code in (405, 501):
            resp = requests.get(
                url,
                timeout=CITATION_CHECK_TIMEOUT_SECONDS,
                allow_redirects=True,
                headers={"User-Agent": _BROWSER_USER_AGENT, "Range": "bytes=0-0"},
                stream=True,
            )
        return resp.status_code < 400 or resp.status_code in _AMBIGUOUS_BLOCKED_STATUSES
    except requests.RequestException:
        return False


def filter_reachable_references(references: list[dict]) -> list[dict]:
    """Checks every reference's `url` concurrently (bounded thread pool, per-request
    timeout) before it's shown as a clickable source; nulls out `url` for anything
    unreachable but keeps `content` - matches AskQuestion.js's existing
    `ref.url ? <a> : ref.content` fallback exactly, so no frontend changes are needed.
    References with no url to begin with (e.g. a tool that returned plain text with no
    artifact) pass through untouched, no network call made."""
    urls = [r["url"] for r in references if r.get("url")]
    if not urls:
        return references

    with ThreadPoolExecutor(max_workers=CITATION_CHECK_MAX_WORKERS) as pool:
        reachability = dict(zip(urls, pool.map(_is_reachable, urls)))

    return [
        {**r, "url": r["url"] if (not r.get("url") or reachability.get(r["url"])) else None}
        for r in references
    ]
