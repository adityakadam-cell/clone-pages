"""Shared helpers: responses, validation, slugs, file parsing."""
import re
from pathlib import Path
from urllib.parse import urlparse


def ok(data=None, message=""):
    return {"ok": True, "data": data or {}, "message": message, "error": ""}


def fail(error, data=None):
    return {"ok": False, "data": data or {}, "message": "", "error": error}


def is_valid_url(url: str) -> bool:
    try:
        p = urlparse(url.strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def slugify(text: str) -> str:
    text = (text or "page").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "page"


def ext_of(filename: str) -> str:
    return Path(filename).suffix.lower()


# --- content extraction ------------------------------------------------
def read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_csv(path: Path) -> str:
    import csv
    rows = []
    with open(path, newline="", encoding="utf-8", errors="ignore") as fh:
        for row in csv.reader(fh):
            rows.append(", ".join(row))
    return "\n".join(rows)


def read_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".txt":
        return read_txt(path)
    if ext == ".csv":
        return read_csv(path)
    if ext == ".docx":
        return read_docx(path)
    if ext == ".pdf":
        return read_pdf(path)
    return ""
