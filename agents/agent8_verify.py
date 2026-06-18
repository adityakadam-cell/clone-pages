"""
Agent 8 — Verify (page vs document).

After the pages are built, re-open each generated HTML file and check it
against its source row/document. Flags anything missing before download:
  * Meta title / Meta description present
  * Page URL present (from the sheet)
  * Design applied (CSS/JS from the reference page)
  * Real content present (not just the product name)
  * The source document's text actually appears in the page
"""
import html as _htmllib
import re
from config import Config
from core.utils import ok

_CONTENT_RE = re.compile(r'<main class="api-agent-content">(.*?)</main>', re.S)
_TITLE_RE = re.compile(r"<title>([^<]*)</title>")
_DESC_RE = re.compile(r'<meta name="description" content="([^"]*)"')
_TAGS_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

MIN_CONTENT_CHARS = 200


def _read_built(filename: str) -> str:
    p = Config.OUTPUT_DIR / filename
    try:
        return p.read_text("utf-8") if p.exists() else ""
    except Exception:
        return ""


def _content_block(html: str) -> str:
    m = _CONTENT_RE.search(html)
    return m.group(1).strip() if m else ""


def _plain(text: str) -> str:
    """Strip tags, decode HTML entities, collapse whitespace, lowercase.
    Both source doc text and the built page run through this so the
    'matches source' check compares like-for-like (the page is escaped at
    build time; the source isn't)."""
    t = _TAGS_RE.sub(" ", text or "")
    t = _htmllib.unescape(t)
    return _WS_RE.sub(" ", t).strip().lower()


def _sources(state):
    return (state.get("agent7", {}).get("approved")
            or state.get("agent5", {}).get("pages")
            or state.get("agent3", {}).get("pages", []))


def run(state):
    built = state.get("built", [])
    by_product = {(p.get("product") or "").strip(): p for p in _sources(state)}

    design = state.get("agent2", {}) or {}
    has_design = bool(design.get("css_links") or design.get("inline_css")
                      or design.get("js_links"))

    reports = []
    for b in built:
        fn = b.get("filename", "")
        product = (b.get("product") or "").strip()
        html = _read_built(fn)
        src = by_product.get(product, {})
        block_plain = _plain(_content_block(html))
        src_plain = _plain(src.get("content", ""))

        checks = []

        def add(name, passed, note=""):
            checks.append({"name": name, "ok": bool(passed), "note": note})

        title = _TITLE_RE.search(html)
        desc = _DESC_RE.search(html)
        add("Meta title", title and title.group(1).strip(),
            (title.group(1).strip() if title else "missing"))
        add("Meta description", desc and desc.group(1).strip(),
            "present" if (desc and desc.group(1).strip()) else "missing")
        add("Page URL", bool((src.get("page_url") or "").strip()),
            src.get("page_url") or "no 'Url (link)' in the sheet")
        add("Design applied", has_design and ("stylesheet" in html or "<script" in html),
            "CSS/JS from the reference page")

        only_name = block_plain in ("", product.lower())
        add("Real content", len(block_plain) >= MIN_CONTENT_CHARS and not only_name,
            f"{len(block_plain)} chars in page body" if block_plain else "page body is empty")

        # Source-document match (normalized text; the page is escaped).
        if len(src_plain) >= 60:
            page_plain = _plain(html)
            windows = [src_plain[:80]]
            if len(src_plain) > 240:
                mid = len(src_plain) // 2
                windows.append(src_plain[mid:mid + 80])
            matched = any(w and w in page_plain for w in windows)
            add("Matches source document", matched,
                "source Doc text found in the page" if matched
                else "page text differs from the source document")
        else:
            add("Source document content", False,
                "the linked Google Doc had no readable content "
                "(empty or not shared 'anyone with the link can view')")

        page_ok = all(ch["ok"] for ch in checks)
        reports.append({"product": product or fn, "filename": fn,
                        "ok": page_ok, "checks": checks})

    issues = sum(1 for r in reports if not r["ok"])
    data = {"reports": reports, "count": len(reports),
            "issues": issues, "all_ok": issues == 0}
    msg = ("All built pages passed the checks." if issues == 0
           else f"{issues} of {len(reports)} page(s) have issues.")
    return ok(data, msg)
