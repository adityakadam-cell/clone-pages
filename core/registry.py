"""
Persistent record of pages already built, so the wizard can skip / flag pages
that were created in an earlier round or session.

Stored as a JSON file next to the generated pages. It survives worker restarts.
(On an ephemeral host like Render's free tier it resets on redeploy — fine for
a working session.)
"""
import json
import time

from config import Config

_REG = Config.OUTPUT_DIR / ".built_registry.json"


def _slug_of(item) -> str:
    slug = item.get("slug")
    if slug:
        return slug
    fn = item.get("filename", "")
    return fn[:-5] if fn.endswith(".html") else fn


def load() -> dict:
    try:
        return json.loads(_REG.read_text("utf-8")) if _REG.exists() else {}
    except Exception:
        return {}


def _save(d: dict):
    try:
        _REG.write_text(json.dumps(d), "utf-8")
    except Exception:
        pass


def mark_built(items):
    """Record built pages (items have product + filename, or slug)."""
    d = load()
    for it in items or []:
        slug = _slug_of(it)
        if slug:
            d[slug] = {"product": it.get("product", ""),
                       "filename": it.get("filename", ""),
                       "at": int(time.time())}
    _save(d)


def built_slugs() -> set:
    return set(load().keys())
