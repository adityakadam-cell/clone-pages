"""
Read a Google Sheet and map the columns the flow needs.

Field mapping (per spec):
  Product          -> page name
  Doc              -> content source (often a HYPERLINK to a Google Doc)
  Meta Title       -> meta_title
  Meta Description -> meta_description
  Url (link)       -> page_url

Two read paths:
  * read_sheet()      — CSV export. Keyless, but Google's CSV export DROPS
                        hyperlinks and keeps only display text. A "Doc" cell
                        that links to a Google Doc comes back as just the
                        product name — no URL.
  * read_sheet_api()  — Sheets API v4 with includeGridData. Exposes each cell's
                        `hyperlink`, so we can recover the Doc link and fetch the
                        real content. Needs a (free) Google API key.
"""
import csv
import io
import re
import requests

COLUMN_MAP = {
    "product": "product",
    "doc": "doc",
    "meta title": "meta_title",
    "meta description": "meta_description",
    "url (link)": "page_url",
    "url(link)": "page_url",
    "web page link": "web_page_link",
}

# Columns whose hyperlink (not display text) is what we actually want.
LINK_FIELDS = {"doc", "page_url", "web_page_link"}


def _sheet_id(sheet_url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sheet_url)
    if not m:
        raise ValueError("Not a valid Google Sheets URL.")
    return m.group(1)


def _gid(sheet_url: str) -> str:
    m = re.search(r"[#&?]gid=(\d+)", sheet_url)
    return m.group(1) if m else "0"


# ---------------------------------------------------------------------- #
# CSV path (keyless, no hyperlinks)
# ---------------------------------------------------------------------- #
def read_sheet(sheet_url: str, limit: int = 500):
    """Return row dicts from the CSV export (display values only)."""
    sid, gid = _sheet_id(sheet_url), _gid(sheet_url)
    export = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}"
    resp = requests.get(export, timeout=30)
    resp.raise_for_status()

    rows = list(csv.reader(io.StringIO(resp.text)))
    if not rows:
        return []

    header = [h.strip().lower() for h in rows[0]]
    mapped_idx = {COLUMN_MAP[h]: i for i, h in enumerate(header) if h in COLUMN_MAP}

    out = []
    for raw in rows[1:limit + 1]:
        rec = {}
        for field, idx in mapped_idx.items():
            rec[field] = raw[idx].strip() if idx < len(raw) else ""
        if rec.get("product"):
            out.append(rec)
    return out


# ---------------------------------------------------------------------- #
# Sheets API path (needs key, exposes hyperlinks)
# ---------------------------------------------------------------------- #
_HYPERLINK_FORMULA = re.compile(r'HYPERLINK\(\s*"([^"]+)"', re.IGNORECASE)


def _cell_value_and_link(cell: dict):
    """Pull (display_value, hyperlink) from one Sheets API cell object."""
    value = (cell.get("formattedValue") or "").strip()
    link = cell.get("hyperlink")
    if not link:
        formula = (cell.get("userEnteredValue", {}) or {}).get("formulaValue")
        if formula:
            m = _HYPERLINK_FORMULA.search(formula)
            if m:
                link = m.group(1)
    return value, (link or "")


def parse_grid(grid_rows: list, limit: int = 500) -> list:
    """Turn Sheets API rowData into mapped row dicts (value + *_link)."""
    if not grid_rows:
        return []

    header_cells = grid_rows[0].get("values", [])
    header = [(c.get("formattedValue") or "").strip().lower() for c in header_cells]
    idx_map = {COLUMN_MAP[h]: i for i, h in enumerate(header) if h in COLUMN_MAP}

    out = []
    for row in grid_rows[1:limit + 1]:
        cells = row.get("values", [])
        rec = {}
        for field, i in idx_map.items():
            value, link = _cell_value_and_link(cells[i]) if i < len(cells) else ("", "")
            rec[field] = value
            if field in LINK_FIELDS:
                rec[f"{field}_link"] = link
        if rec.get("product"):
            out.append(rec)
    return out


def read_sheet_api(sheet_url: str, api_key: str, limit: int = 500) -> list:
    """Read the sheet via Sheets API v4 so hyperlinks survive."""
    sid, gid = _sheet_id(sheet_url), _gid(sheet_url)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}"
    params = {
        "includeGridData": "true",
        "key": api_key,
        "fields": (
            "sheets(properties(sheetId,title),"
            "data(rowData(values(formattedValue,hyperlink,userEnteredValue))))"
        ),
    }
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    sheets = resp.json().get("sheets", [])
    if not sheets:
        return []

    sheet = next(
        (s for s in sheets if str(s["properties"].get("sheetId")) == str(gid)),
        sheets[0],
    )
    data = sheet.get("data", [{}])
    grid_rows = (data[0] if data else {}).get("rowData", [])
    return parse_grid(grid_rows, limit=limit)
