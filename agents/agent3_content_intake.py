"""
Agent 3 — Content intake.

Two modes:
  A) File upload  : 1-10 files, only .docx/.pdf/.csv/.txt
  B) Google Sheet : read mapped columns (Product, Doc, Meta Title,
                    Meta Description, Url (link)). The Doc cell usually links
                    to a Google Doc, so the real content is fetched from that
                    link (needs a Google API key to recover the hyperlink and
                    to read the Doc via the Docs API).
"""
import uuid
from werkzeug.utils import secure_filename

from config import Config
from core.utils import ok, fail, ext_of, extract_text, slugify
from core.sheet_reader import read_sheet, read_sheet_api
from core.doc_fetcher import is_url, safe_fetch


def run_files(files):
    files = [f for f in files if f and f.filename]
    n = len(files)

    if n < Config.MIN_UPLOAD_FILES:
        return fail("Upload at least 1 file.")
    if n > Config.MAX_UPLOAD_FILES:
        return fail(f"Too many files. Max {Config.MAX_UPLOAD_FILES} per round.")

    bad = [f.filename for f in files if ext_of(f.filename) not in Config.ALLOWED_EXTENSIONS]
    if bad:
        allowed = ", ".join(sorted(Config.ALLOWED_EXTENSIONS))
        return fail(f"Unsupported file(s): {', '.join(bad)}. Allowed: {allowed}.")

    pages = []
    for f in files:
        safe = secure_filename(f.filename)
        dest = Config.UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{safe}"
        f.save(dest)
        try:
            text = extract_text(dest)
        except Exception as exc:  # pragma: no cover
            return fail(f"Could not read {f.filename}: {exc}")
        name = safe.rsplit(".", 1)[0]
        pages.append({
            "product": name,
            "slug": slugify(name),
            "content": text,
            "source": safe,
            "page_url": "",
            "meta_title": "",
            "meta_description": "",
        })
    return ok({"mode": "files", "pages": pages, "count": len(pages)},
              f"Loaded {len(pages)} file(s).")


def _doc_content(rec, api_key: str = ""):
    """Resolve the real content for a sheet row.

    Order of preference:
      1. Doc hyperlink (from the Sheets API)  -> fetch that doc's text
      2. Doc cell value that is itself a URL  -> fetch it
      3. Doc cell plain text                  -> use as-is
    Returns (content, note) where note flags fetch problems.
    """
    link = (rec.get("doc_link") or "").strip()
    value = (rec.get("doc") or "").strip()

    target = link or (value if is_url(value) else "")
    if target:
        text, err, resolved = safe_fetch(target, api_key=api_key,
                                         prefer_title=Config.DOC_TAB_TITLE)
        if text:
            return text, "", resolved          # link points at the tab used
        return value, f"could not fetch doc link ({err})", target
    return value, "", target


def run_sheet(sheet_url, api_key: str = ""):
    if not sheet_url or not sheet_url.strip():
        return fail("Paste a Google Sheet link.")

    sheet_url = sheet_url.strip()
    used_api = False
    try:
        if api_key:
            rows = read_sheet_api(sheet_url, api_key)
            used_api = True
        else:
            rows = read_sheet(sheet_url)
    except Exception as exc:
        return fail(f"Could not read sheet: {exc}")
    if not rows:
        return fail("No rows found. Is the sheet shared as 'anyone with link'?")

    pages, fetched, notes, created = [], 0, [], 0
    for r in rows:
        # A ticked "Created" column means: skip this row, do not rebuild it.
        done = bool(r.get("status_done"))
        if done:
            created += 1
        content, note, doc_url = ("", "", (r.get("doc_link") or ""))
        if not done:
            content, note, doc_url = _doc_content(r, api_key=api_key)
            if note:
                notes.append(f"{r.get('product','?')}: {note}")
            if content and content != (r.get("doc") or "").strip():
                fetched += 1
        pages.append({
            "product": r.get("product", ""),
            "slug": slugify(r.get("product", "")),
            "content": content,
            "doc_url": (doc_url or r.get("doc_link") or ""),
            "page_url": (r.get("page_url_link") or r.get("page_url", "")),
            "meta_title": r.get("meta_title", ""),
            "meta_description": r.get("meta_description", ""),
            "source": "google-sheet",
            "status_done": done,
            "_note": note,
        })

    msg = f"Read {len(pages)} rows; fetched content for {fetched} page(s)."
    if created:
        msg += f"  {created} row(s) already ticked 'Created' -> will be skipped."
    if not used_api:
        msg += (" (No Google API key set - Doc links can't be read, so "
                "content was taken from the cell text only.)")
    elif notes:
        msg += f"  First issue -> {notes[0]}"
    data = {"mode": "sheet", "pages": pages, "count": len(pages),
            "fetched": fetched, "used_api": used_api, "notes": notes[:20],
            "created_skipped": created}
    return ok(data, msg)
