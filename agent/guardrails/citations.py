from concurrent.futures import ThreadPoolExecutor

import requests

from config import CITATION_CHECK_MAX_WORKERS, CITATION_CHECK_TIMEOUT_SECONDS


def _is_reachable(url: str) -> bool:
    """Same fail-closed style as tools/price.py/tools/search.py: any exception means
    'not confirmed reachable', never raised. HEAD first (cheaper); falls back to a
    ranged GET for servers that don't support HEAD (405/501) or block it outright."""
    try:
        resp = requests.head(url, timeout=CITATION_CHECK_TIMEOUT_SECONDS, allow_redirects=True)
        if resp.status_code in (405, 501):
            resp = requests.get(
                url,
                timeout=CITATION_CHECK_TIMEOUT_SECONDS,
                allow_redirects=True,
                headers={"Range": "bytes=0-0"},
                stream=True,
            )
        return resp.status_code < 400
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
