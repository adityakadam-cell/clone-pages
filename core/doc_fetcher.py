"""
Fetch real page content from a link found in a sheet's "Doc" cell.

Google Docs are read in this order:
  1. Docs API v1 with includeTabsContent  -> walks tabs + body, handles the
     newer "tabs" feature that the plain text export silently drops.
     (Needs the Docs API enabled + allowed on the key, and a public doc.)
  2. Fallback: …/export?format=txt          -> works for simple, public docs.
Any non-Google URL is fetched and stripped to readable text.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

TIMEOUT = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (API-Agent content fetcher)"}
DOCS_API = "https://docs.googleapis.com/v1/documents/"

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


# ---------------------------------------------------------------------- #
# Docs API v1 (handles tabs)
# ---------------------------------------------------------------------- #
def _walk_structural(content) -> str:
    """Pull text out of a Docs API body 'content' list."""
    out = []
    for el in content or []:
        para = el.get("paragraph")
        if para:
            for e in para.get("elements", []):
                tr = e.get("textRun")
                if tr and tr.get("content"):
                    out.append(tr["content"])
        table = el.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    out.append(_walk_structural(cell.get("content")))
        toc = el.get("tableOfContents")
        if toc:
            out.append(_walk_structural(toc.get("content")))
    return "".join(out)


def _walk_tabs(tabs) -> str:
    out = []
    for tab in tabs or []:
        body = (tab.get("documentTab", {}) or {}).get("body", {}) or {}
        out.append(_walk_structural(body.get("content")))
        out.append(_walk_tabs(tab.get("childTabs")))
    return "".join(out)


def fetch_gdoc_via_api(doc_id: str, api_key: str) -> str:
    """Read a public Google Doc (incl. tabs) via the Docs API. Raises on error."""
    r = requests.get(
        f"{DOCS_API}{doc_id}",
        params={"key": api_key, "includeTabsContent": "true"},
        timeout=TIMEOUT, headers=HEADERS,
    )
    r.raise_for_status()
    data = r.json()
    text = _walk_tabs(data.get("tabs"))
    if not text.strip():
        text = _walk_structural((data.get("body", {}) or {}).get("content"))
    return _tidy(text)


def _tidy(text: str) -> str:
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    out, blank = [], 0
    for ln in lines:
        if ln.strip():
            out.append(ln); blank = 0
        else:
            blank += 1
            if blank <= 1:
                out.append("")
    return "\n".join(out).strip()


# ---------------------------------------------------------------------- #
# Fallbacks
# ---------------------------------------------------------------------- #
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


def fetch_doc_text(url: str, api_key: str = "") -> str:
    """Return plain-text content for a Doc link. Raises on failure / private doc."""
    did = gdoc_id(url)

    # 1. Docs API (handles tabs) when we have a key
    if did and api_key:
        try:
            text = fetch_gdoc_via_api(did, api_key)
            if text:
                return text
        except Exception:
            pass  # fall through to the export

    # 2. Plain txt export (simple public docs)
    export = gdoc_export_url(url)
    target = export or url
    r = requests.get(target, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True)
    r.raise_for_status()

    if export:
        text = (r.text or "").strip()
        if not text:
            raise RuntimeError("empty doc, or it uses tabs and isn't readable "
                               "via export (enable the Docs API), or it's not shared")
        if _looks_like_login(text):
            raise RuntimeError("doc is private — share it 'anyone with the link can view'")
        return _tidy(text)

    return _html_to_text(r.text)


def safe_fetch(url: str, api_key: str = "") -> tuple[str, str]:
    """Fetch without raising. Returns (text, error)."""
    if not is_url(url):
        return "", "not a url"
    try:
        return fetch_doc_text(url, api_key=api_key), ""
    except Exception as exc:        # pragma: no cover - network dependent
        return "", str(exc)
