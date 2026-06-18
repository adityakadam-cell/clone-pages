"""
Fetch real page content from a link found in a sheet's "Doc" cell.

Handles:
  * Google Docs  -> export as plain text (…/export?format=txt)
  * Any other URL -> fetch HTML and strip to readable text

Note: a Google Doc that is NOT shared "anyone with the link can view" will
redirect the export endpoint to a sign-in page instead of returning text.
We detect that and raise a clear error so Agent 3 can flag it.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

TIMEOUT = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (API-Agent content fetcher)"}

_GDOC_RE = re.compile(r"docs\.google\.com/document/d/([a-zA-Z0-9-_]+)")


def is_url(value: str) -> bool:
    try:
        p = urlparse((value or "").strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def gdoc_id(url: str) -> str | None:
    m = _GDOC_RE.search(url or "")
    return m.group(1) if m else None


def gdoc_export_url(url: str) -> str | None:
    did = gdoc_id(url)
    return f"https://docs.google.com/document/d/{did}/export?format=txt" if did else None


def _looks_like_login(text: str) -> bool:
    head = (text or "")[:800].lower()
    return any(s in head for s in (
        "<html", "sign in", "accounts.google.com",
        "request access", "you need permission", "needs permission",
    ))


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    lines = (ln.strip() for ln in soup.get_text("\n").splitlines())
    return "\n".join(ln for ln in lines if ln)


def fetch_doc_text(url: str) -> str:
    """Return plain-text content for a Doc link. Raises on failure / private doc."""
    export = gdoc_export_url(url)
    target = export or url
    r = requests.get(target, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True)
    r.raise_for_status()

    if export:
        text = (r.text or "").strip()
        if not text:
            raise RuntimeError("empty doc, or not shared publicly")
        if _looks_like_login(text):
            raise RuntimeError("doc is private — share it 'anyone with the link can view'")
        return text

    return _html_to_text(r.text)


def safe_fetch(url: str) -> tuple[str, str]:
    """Fetch without raising. Returns (text, error)."""
    if not is_url(url):
        return "", "not a url"
    try:
        return fetch_doc_text(url), ""
    except Exception as exc:        # pragma: no cover - network dependent
        return "", str(exc)
