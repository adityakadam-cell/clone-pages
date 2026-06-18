"""
Agent 8 — Verify (page vs document).

After the pages are built, re-open each generated HTML file and check it
against its source row/document. Flags anything missing so the user knows a
page is incomplete BEFORE downloading:

  * Meta title present
  * Meta description present
  * Page URL present (from the sheet)
  * Design applied (CSS/JS from the reference page)
  * Real content present (not just the product name)
  * The source document's text actually appears in the page
"""
import re
from config import Config
from core.utils import ok

_CONTENT_RE = re.compile(r'<main class="api-agent-content">(.*?)</main>', re.S)
_TITLE_RE = re.compile(r"<title>([^<]*)</title>")
_DESC_RE = re.compile(r'<meta name="description" content="([^"]*)"')
_TAGS_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

MIN_CONTENT_CHARS = 200   # a real page body should be at least this long


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
    return _WS_RE.sub(" ", _TAGS_RE.sub(" ", text or "")).strip()


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

        # Real content: must be longer than just the product name.
        only_name = block_plain.lower() in ("", product.lower())
        add("Real content", len(block_plain) >= MIN_CONTENT_CHARS and not only_name,
            f"{len(block_plain)} chars in page body"
            if block_plain else "page body is empty")

        # Source-document match.
        if len(src_plain) >= 60:
            sample = src_plain[:80]
            add("Matches source document", sample and sample in _plain(html),
                "source Doc text found in the page")
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
