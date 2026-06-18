"""
Agent 4 — Loading & analysis.

Scan everything gathered so far and raise a 'requirements board' of anything
missing. For every page it lists the product (page) name plus, for each missing
field, WHY it is missing from the sheet.
"""
from core.utils import ok

REQUIRED_PAGE_FIELDS = ["product", "content", "page_url", "meta_title", "meta_description"]

# Friendly labels + the reason a field would be missing from the Google Sheet.
FIELD_LABEL = {
    "product": "Product (page name)",
    "content": "Content",
    "page_url": "Page URL",
    "meta_title": "Meta Title",
    "meta_description": "Meta Description",
}
FIELD_REASON = {
    "product": "The 'Product' column is blank in this row.",
    "content": "The 'Doc' cell is empty — no Google Doc is linked, "
               "or the linked Doc isn't shared 'anyone with the link can view'.",
    "page_url": "The 'Url (link)' column is blank in this row.",
    "meta_title": "The 'Meta Title' column is blank in this row.",
    "meta_description": "The 'Meta Description' column is blank in this row.",
}


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
                "product": page.get("product") or f"page {i + 1}",
                "page_url": page.get("page_url", ""),
                "missing": missing,
                # field-by-field reason for the cards
                "missing_detail": [
                    {"field": f, "label": FIELD_LABEL.get(f, f),
                     "reason": FIELD_REASON.get(f, "Not provided in the sheet.")}
                    for f in missing
                ],
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
