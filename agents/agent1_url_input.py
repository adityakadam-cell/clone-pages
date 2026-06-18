"""Agent 1 — Page URL input. Validates the reference page URL."""
from urllib.parse import urlparse
from core.utils import ok, fail, is_valid_url


def run(url: str):
    url = (url or "").strip()
    if not url:
        return fail("Please enter a page URL.")
    if not is_valid_url(url):
        return fail("That doesn't look like a valid http(s) URL.")
    host = urlparse(url).netloc
    return ok({"url": url, "host": host}, f"URL accepted ({host}).")
