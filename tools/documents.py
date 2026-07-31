import re
from io import BytesIO

import requests
from pypdf import PdfReader

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

_TAG_RE = re.compile(r"<[^>]+>")


def extract_text(raw: bytes, content_type: str | None, filename_or_url: str) -> str:
    """PDF via pypdf if the content-type or extension says so. HTML gets its tags
    stripped (cheap regex, no parsing dependency) rather than left as markup noise in
    the chunked text. Anything else is decoded as plain UTF-8 text."""
    is_pdf = (content_type and "pdf" in content_type.lower()) or filename_or_url.lower().endswith(".pdf")
    if is_pdf:
        reader = PdfReader(BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    text = raw.decode("utf-8", errors="replace")
    is_html = content_type and "html" in content_type.lower()
    if is_html:
        return _TAG_RE.sub(" ", text)
    return text


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Fixed-size sliding-window chunking - no sentence/paragraph awareness, just enough
    to keep each embedded chunk a bounded, overlapping slice of the source text."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += size - overlap
    return chunks


def fetch_link(url: str) -> tuple[bytes, str | None]:
    """Server-side fetch of a pasted link, same requests-based approach used for news
    fetching elsewhere. Returns (raw bytes, content-type header)."""
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.content, resp.headers.get("content-type")
