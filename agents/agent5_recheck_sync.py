"""
Agent 5 — Recheck & sync.

Re-walk the content + design. For any field still missing, auto-build a
sensible default so the page is complete and matches the design. Also returns
a per-page summary (product, content doc URL, page URL, meta title/description)
so the Sync screen shows exactly what will go into each page.
"""
from core.utils import ok, slugify


def _autofill(page):
    fixes = []
    product = page.get("product") or "Untitled Page"

    if not page.get("slug"):
        page["slug"] = slugify(product)

    if not str(page.get("meta_title", "")).strip():
        page["meta_title"] = f"{product} Manufacturer & Supplier"
        fixes.append("meta_title")

    if not str(page.get("meta_description", "")).strip():
        page["meta_description"] = (
            f"{product} with reliable quality, durability and performance "
            f"for industrial applications.")
        fixes.append("meta_description")

    if not str(page.get("content", "")).strip():
        page["content"] = f"<h2>{product}</h2><p>Content pending review.</p>"
        fixes.append("content")

    if not str(page.get("page_url", "")).strip():
        page["page_url"] = f"/{page['slug']}.html"
        fixes.append("page_url")

    return fixes


def run(state):
    content = state.get("agent3", {})
    pages = content.get("pages", [])

    synced, rows = [], []
    for page in pages:
        page = dict(page)
        fixes = _autofill(page)
        page["_autofilled"] = fixes
        synced.append(page)

        body = str(page.get("content", "") or "")
        rows.append({
            "product": page.get("product", ""),
            "doc_url": page.get("doc_url", ""),
            "page_url": page.get("page_url", ""),
            "meta_title": page.get("meta_title", ""),
            "meta_description": page.get("meta_description", ""),
            "content_chars": len(body.strip()),
            "autofilled": fixes,
            "status_done": bool(page.get("status_done")),
        })

    total_fixes = sum(len(p["_autofilled"]) for p in synced)
    data = {"pages": synced, "rows": rows, "auto_fixes": total_fixes}
    return ok(data, f"Synced {len(synced)} page(s); auto-built {total_fixes} missing field(s).")
