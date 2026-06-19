"""
Read a Google Sheet and map the columns the flow needs.

Field mapping (per spec):
  Product          -> page name
  Doc              -> content source (usually a Google "smart chip" link to a Doc)
  Meta Title       -> meta_title
  Meta Description -> meta_description
  Url (link)       -> page_url

Two read paths:
  * read_sheet()      — CSV export. Keyless, but Google's CSV export DROPS all
                        links and keeps only display text.
  * read_sheet_api()  — Sheets API v4 with includeGridData. Exposes a cell's
                        links so we can recover the Doc URL. Links can live in
                        THREE places, so we check all of them:
                          1. cell.hyperlink              (whole-cell link)
                          2. =HYPERLINK("...") formula   (formula link)
                          3. chipRuns[].chip.richLinkProperties.uri  (smart chip)
                          4. textFormatRuns[].format.link.uri        (rich text)
                        Needs a (free) Google API key.
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
    "created": "created",
    "created?": "created",
    "is created": "created",
    "page created": "created",
    "status": "created",
    "page status": "created",
    "done": "created",
}

# Values in the "Created" column that mean "already done -> skip this row".
TICK_WORDS = {"true", "yes", "y", "done", "created", "complete", "completed",
              "x", "1", "✓", "✔", "✅", "✔️"}


def _is_done(value, cell=None):
    """A row is 'done' when its Created cell is a ticked checkbox (boolValue
    True) or holds a yes/done-style value."""
    if cell is not None:
        bv = (cell.get("userEnteredValue", {}) or {}).get("boolValue")
        if bv is True:
            return True
        if bv is False:
            return False
    return (value or "").strip().lower() in TICK_WORDS

# Columns whose link (not display text) is what we actually want.
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
# CSV path (keyless, no links)
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
            val = raw[idx].strip() if idx < len(raw) else ""
            rec[field] = val
            if field == "created":
                rec["status_done"] = _is_done(val)
        rec.setdefault("status_done", False)
        if rec.get("product"):
            out.append(rec)
    return out


# ---------------------------------------------------------------------- #
# Sheets API path (needs key, exposes links)
# ---------------------------------------------------------------------- #
_HYPERLINK_FORMULA = re.compile(r'HYPERLINK\(\s*"([^"]+)"', re.IGNORECASE)


def _link_from_cell(cell: dict) -> str:
    """Find a link in a cell, checking every place Google may store one."""
    # 1. whole-cell hyperlink
    link = cell.get("hyperlink")
    if link:
        return link

    # 2. =HYPERLINK("...") formula
    formula = (cell.get("userEnteredValue", {}) or {}).get("formulaValue")
    if formula:
        m = _HYPERLINK_FORMULA.search(formula)
        if m:
            return m.group(1)

    # 3. smart chip (Insert > Smart chip, or paste a Doc link as a chip)
    for run in cell.get("chipRuns", []) or []:
        uri = ((run.get("chip", {}) or {}).get("richLinkProperties", {}) or {}).get("uri")
        if uri:
            return uri

    # 4. rich-text run link (link applied to selected text inside the cell)
    for run in cell.get("textFormatRuns", []) or []:
        uri = ((run.get("format", {}) or {}).get("link", {}) or {}).get("uri")
        if uri:
            return uri

    return ""


def _cell_value_and_link(cell: dict):
    value = (cell.get("formattedValue") or "").strip()
    return value, _link_from_cell(cell)


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
            cell = cells[i] if i < len(cells) else {}
            value, link = _cell_value_and_link(cell)
            rec[field] = value
            if field in LINK_FIELDS:
                rec[f"{field}_link"] = link
            if field == "created":
                rec["status_done"] = _is_done(value, cell)
        rec.setdefault("status_done", False)
        if rec.get("product"):
            out.append(rec)
    return out


def read_sheet_api(sheet_url: str, api_key: str, limit: int = 500) -> list:
    """Read the sheet via Sheets API v4 so links survive."""
    sid, gid = _sheet_id(sheet_url), _gid(sheet_url)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}"
    params = {
        "includeGridData": "true",
        "key": api_key,
        "fields": (
            "sheets(properties(sheetId,title),data(rowData(values("
            "formattedValue,hyperlink,userEnteredValue,chipRuns,textFormatRuns))))"
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
