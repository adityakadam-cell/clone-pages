"""
Agent 4 — Loading & analysis.

Scan everything gathered so far and raise a 'requirements board' of
anything missing, so the user can go Back and fix it.
"""
from core.utils import ok

REQUIRED_PAGE_FIELDS = ["product", "content", "page_url", "meta_title", "meta_description"]


def run(state):
    board = []          # global requirements
    page_issues = []    # per-page requirements

    if not state.get("agent1"):
        board.append("Agent 1: page URL not set.")
    if not state.get("agent2"):
        board.append("Agent 2: design (CSS/JS) not captured.")

    content = state.get("agent3", {})
    pages = content.get("pages", [])
    if not pages:
        board.append("Agent 3: no content uploaded or read.")

    for i, page in enumerate(pages):
        missing = [f for f in REQUIRED_PAGE_FIELDS if not str(page.get(f, "")).strip()]
        if missing:
            page_issues.append({
                "index": i,
                "product": page.get("product", f"page {i+1}"),
                "missing": missing,
            })

    complete = not board and not page_issues
    data = {
        "board": board,
        "page_issues": page_issues,
        "total_pages": len(pages),
        "pages_with_issues": len(page_issues),
        "complete": complete,
    }
    msg = "Everything looks complete." if complete else \
        f"{len(board)} global and {len(page_issues)} page issue(s) found."
    return ok(data, msg)
