"""
Service-account OAuth for the Google Docs API.

The Docs API does NOT accept API keys (returns 401), so reading Doc content
needs an OAuth access token. A service account provides one without any user
sign-in. Set GOOGLE_SERVICE_ACCOUNT_JSON to the JSON key (a file path or the
raw JSON string). The service account can read any Doc shared "anyone with the
link", or docs explicitly shared with its client_email.
"""
import json
import threading
from pathlib import Path

from config import Config

SCOPES = [
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

_lock = threading.Lock()
_state = {"loaded": False, "creds": None}


def _account_info():
    raw = (Config.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
    if not raw:
        return None
    # a file path?
    try:
        p = Path(raw)
        if len(raw) < 500 and p.exists():
            return json.loads(p.read_text("utf-8"))
    except Exception:
        pass
    # raw JSON string?
    try:
        return json.loads(raw)
    except Exception:
        return None


def _credentials():
    with _lock:
        if _state["loaded"]:
            return _state["creds"]
        _state["loaded"] = True
        info = _account_info()
        if not info:
            return None
        try:
            from google.oauth2 import service_account
            _state["creds"] = service_account.Credentials.from_service_account_info(
                info, scopes=SCOPES)
        except Exception:
            _state["creds"] = None
        return _state["creds"]


def get_token() -> str | None:
    """A fresh OAuth bearer token, or None if no service account is configured."""
    creds = _credentials()
    if not creds:
        return None
    try:
        from google.auth.transport.requests import Request
        if not creds.valid:
            creds.refresh(Request())
        return creds.token
    except Exception:
        return None


def is_configured() -> bool:
    return _credentials() is not None
