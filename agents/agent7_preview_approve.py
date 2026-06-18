"""
Agent 7 — Preview & approve.

Render a lightweight preview for each page and let the user approve the
ones that should proceed to download (Agent 6).
"""
from core.utils import ok


def _pages(state):
    a5 = state.get("agent5", {})
    if a5.get("pages"):
        return a5["pages"]
    return state.get("agent3", {}).get("pages", [])


def preview(state):
    pages = _pages(state)
    items = []
    for i, p in enumerate(pages):
        items.append({
            "id": i,
            "product": p.get("product", f"page {i+1}"),
            "meta_title": p.get("meta_title", ""),
            "meta_description": p.get("meta_description", ""),
            "page_url": p.get("page_url", ""),
            "content_preview": (p.get("content", "") or "")[:280],
        })
    return ok({"items": items, "count": len(items)})


def approve(state, approved_ids):
    pages = _pages(state)
    approved_ids = set(int(i) for i in approved_ids)
    approved = [p for i, p in enumerate(pages) if i in approved_ids]
    return ok({"approved": approved, "count": len(approved)},
              f"{len(approved)} page(s) approved.")
