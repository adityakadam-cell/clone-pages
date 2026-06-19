"""
Agent 7 — Preview & approve.

Shows only the next batch (MAX_BUILD_PAGES) of pages that have NOT been built
yet, so a big sheet is worked through 5 at a time. Pages built in an earlier
round/session are remembered (registry) and reported so the user knows they
were already done.
"""
from config import Config
from core.utils import ok
from core import registry


def _pages(state):
    a5 = state.get("agent5", {})
    if a5.get("pages"):
        return a5["pages"]
    return state.get("agent3", {}).get("pages", [])


def _slug(p, i):
    return p.get("slug") or f"page-{i}"


def preview(state):
    pages = _pages(state)
    done = registry.built_slugs()

    todo, already = [], []
    for i, p in enumerate(pages):
        is_done = _slug(p, i) in done or bool(p.get("status_done"))
        (already if is_done else todo).append((i, p))

    batch = todo[:Config.MAX_BUILD_PAGES]          # only the next 5
    items = [{
        "id": i,                                    # original index (approve uses it)
        "product": p.get("product", f"page {i+1}"),
        "meta_title": p.get("meta_title", ""),
        "meta_description": p.get("meta_description", ""),
        "page_url": p.get("page_url", ""),
        "content_preview": (p.get("content", "") or "")[:280],
    } for i, p in batch]

    done_names = [p.get("product", "") for _, p in already][:50]

    return ok({
        "items": items,
        "count": len(items),
        "total": len(pages),
        "todo_total": len(todo),
        "done_count": len(already),
        "done_names": done_names,
        "batch_size": Config.MAX_BUILD_PAGES,
    })


def approve(state, approved_ids):
    pages = _pages(state)
    ids = set(int(i) for i in approved_ids)
    approved = [p for i, p in enumerate(pages) if i in ids]
    return ok({"approved": approved, "count": len(approved)},
              f"{len(approved)} page(s) approved.")
