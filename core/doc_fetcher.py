"""
Fetch real page content from a link found in a sheet's "Doc" cell.

Google Docs are read via the Docs API v1 (includeTabsContent). The Docs API
REJECTS API keys (401), so a service-account bearer token is used when
configured (GOOGLE_SERVICE_ACCOUNT_JSON). When a doc has multiple tabs we
return ONLY one tab, chosen by:
  1. the tab whose TITLE matches prefer_title (e.g. "Final") — most reliable,
     because chip links in sheets can point at the wrong tab id;
  2. the tab id named in the link (…/edit?tab=t.xxxxx).
If a specific tab was requested but can't be isolated, we raise a clear error
instead of dumping every tab. Inline images become an [[IMAGE]] marker.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

TIMEOUT = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (API-Agent content fetcher)"}
DOCS_API = "https://docs.googleapis.com/v1/documents/"
IMAGE_MARK = "[[IMAGE]]"

_GDOC_RE = re.compile(r"docs\.google\.com/document/d/([a-zA-Z0-9-_]+)")
_TAB_RE = re.compile(r"[?#&]tab=(t\.[a-zA-Z0-9]+)")


class TabNotFound(Exception):
    pass


def is_url(value: str) -> bool:
    try:
        p = urlparse((value or "").strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def gdoc_id(url: str) -> str | None:
    m = _GDOC_RE.search(url or "")
    return m.group(1) if m else None


def gdoc_tab_id(url: str) -> str | None:
    m = _TAB_RE.search(url or "")
    return m.group(1) if m else None


def gdoc_export_url(url: str) -> str | None:
    did = gdoc_id(url)
    return f"https://docs.google.com/document/d/{did}/export?format=txt" if did else None


# ---------------------------------------------------------------------- #
# Docs API v1 (tabs)
# ---------------------------------------------------------------------- #
def _walk_structural(content) -> str:
    out = []
    for el in content or []:
        para = el.get("paragraph")
        if para:
            for e in para.get("elements", []):
                tr = e.get("textRun")
                if tr and tr.get("content"):
                    out.append(tr["content"])
                if "inlineObjectElement" in e:
                    out.append(f"\n{IMAGE_MARK}\n")
            out.append("\n")
        table = el.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    out.append(_walk_structural(cell.get("content")))
        toc = el.get("tableOfContents")
        if toc:
            out.append(_walk_structural(toc.get("content")))
    return "".join(out)


def _tab_id_match(api_id: str, want: str) -> bool:
    if not api_id or not want:
        return False
    a, w = api_id.lower().strip(), want.lower().strip()
    a2 = a[2:] if a.startswith("t.") else a
    w2 = w[2:] if w.startswith("t.") else w
    return a == w or a2 == w2 or a.endswith(w) or w.endswith(a)


def _find_tab_by_title(tabs, title):
    want = (title or "").lower().strip()
    if not want:
        return None
    for tab in tabs or []:
        if ((tab.get("tabProperties", {}) or {}).get("title", "")
                .lower().strip() == want):
            return tab
        found = _find_tab_by_title(tab.get("childTabs"), title)
        if found:
            return found
    return None


def _find_tab_by_id(tabs, tab_id):
    for tab in tabs or []:
        if _tab_id_match((tab.get("tabProperties", {}) or {}).get("tabId", ""), tab_id):
            return tab
        found = _find_tab_by_id(tab.get("childTabs"), tab_id)
        if found:
            return found
    return None


def _tab_body_text(tab) -> str:
    body = (tab.get("documentTab", {}) or {}).get("body", {}) or {}
    return _tidy(_walk_structural(body.get("content")))


def _walk_tabs(tabs) -> str:
    out = []
    for tab in tabs or []:
        body = (tab.get("documentTab", {}) or {}).get("body", {}) or {}
        out.append(_walk_structural(body.get("content")))
        out.append(_walk_tabs(tab.get("childTabs")))
    return "".join(out)


def fetch_gdoc_via_api(doc_id: str, api_key: str,
                       tab_id: str | None = None,
                       prefer_title: str | None = None) -> str:
    # The Docs API rejects API keys (401). Use a service-account bearer token
    # when configured; only fall back to the key (which will 401) otherwise.
    from core.google_auth import get_token
    token = get_token()
    headers = dict(HEADERS)
    params = {"includeTabsContent": "true"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        params["key"] = api_key

    r = requests.get(f"{DOCS_API}{doc_id}", params=params,
                     timeout=TIMEOUT, headers=headers)
    r.raise_for_status()
    data = r.json()
    tabs = data.get("tabs")

    if tabs:
        tab = (_find_tab_by_title(tabs, prefer_title) if prefer_title else None)
        if tab is None and tab_id:
            tab = _find_tab_by_id(tabs, tab_id)
        if tab is not None:
            return _tab_body_text(tab)
        if prefer_title or tab_id:
            raise TabNotFound(prefer_title or tab_id)
        return _tidy(_walk_tabs(tabs))

    return _tidy(_walk_structural((data.get("body", {}) or {}).get("content")))


def _tidy(text: str) -> str:
    text = (text or "").replace("﻿", "")
    lines = [ln.rstrip() for ln in text.splitlines()]
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


def fetch_doc_text(url: str, api_key: str = "", prefer_title: str = "") -> str:
    """Return plain-text content for a Doc link. Prefers the tab titled
    prefer_title, else the tab named in the link."""
    from core.google_auth import is_configured

    did = gdoc_id(url)
    tab_id = gdoc_tab_id(url)
    wants_tab = bool(prefer_title or tab_id)

    if did and (api_key or is_configured()):
        try:
            text = fetch_gdoc_via_api(did, api_key, tab_id=tab_id,
                                      prefer_title=prefer_title or None)
            if text:
                return text
            if wants_tab:
                raise RuntimeError("the linked Doc tab is empty")
        except TabNotFound:
            raise RuntimeError(
                f"couldn't find a '{prefer_title}' tab (or the linked tab) in the "
                "Doc — check the tab name, or re-copy the tab link into the Doc cell")
        except RuntimeError:
            raise
        except Exception as exc:
            if wants_tab:
                raise RuntimeError(
                    f"couldn't read the Doc via the Docs API ({exc}). The Docs API "
                    "needs a service account (it rejects API keys) — set "
                    "GOOGLE_SERVICE_ACCOUNT_JSON. Also ensure the Doc is shared.")

    export = gdoc_export_url(url)
    target = export or url
    r = requests.get(target, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True)
    r.raise_for_status()
    if export:
        text = (r.text or "").strip()
        if not text:
            raise RuntimeError("empty doc, or it uses tabs and isn't readable "
                               "via export (use a service account), or it's not shared")
        if _looks_like_login(text):
            raise RuntimeError("doc is private — share it 'anyone with the link can view'")
        return _tidy(text)
    return _html_to_text(r.text)


def safe_fetch(url: str, api_key: str = "", prefer_title: str = "") -> tuple[str, str]:
    if not is_url(url):
        return "", "not a url"
    try:
        return fetch_doc_text(url, api_key=api_key, prefer_title=prefer_title), ""
    except Exception as exc:        # pragma: no cover - network dependent
        return "", str(exc)
