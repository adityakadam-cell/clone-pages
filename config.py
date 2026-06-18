"""Central configuration for the API-Agent app."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # Google API key with the Sheets + Docs APIs enabled. Required to read
    # Doc-cell links and the Doc content. Free to create.
    GOOGLE_API_KEY = (os.environ.get("GOOGLE_API_KEY") or "").strip()

    # Service-account JSON (file path OR the raw JSON string). REQUIRED to read
    # Google Docs — the Docs API rejects API keys (401). The service account
    # reads any doc shared "anyone with the link" (or shared with its email).
    GOOGLE_SERVICE_ACCOUNT_JSON = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()

    # Folders
    UPLOAD_DIR = BASE_DIR / "uploads"
    OUTPUT_DIR = BASE_DIR / "output"

    # Upload rules (Agent 3)
    ALLOWED_EXTENSIONS = {".docx", ".pdf", ".csv", ".txt"}
    MIN_UPLOAD_FILES = 1
    MAX_UPLOAD_FILES = int(os.environ.get("MAX_UPLOAD_FILES", 10))
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", 15))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024 * MAX_UPLOAD_FILES

    # Ordered flow. Agent 7 (preview/approve) and 8 (verify) run before download.
    AGENT_ORDER = [1, 2, 3, 4, 5, 7, 8, 6]

    # Max pages that can be approved & built in one round.
    MAX_BUILD_PAGES = int(os.environ.get("MAX_BUILD_PAGES", 5))

    # When a Doc has multiple tabs, prefer the tab with this title (case-
    # insensitive). The chip's tab id is only a fallback. Set "" to disable.
    DOC_TAB_TITLE = os.environ.get("DOC_TAB_TITLE", "Final").strip()


def init_dirs():
    Config.UPLOAD_DIR.mkdir(exist_ok=True)
    Config.OUTPUT_DIR.mkdir(exist_ok=True)
