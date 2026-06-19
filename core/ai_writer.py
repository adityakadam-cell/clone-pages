"""
AI writer — the "creative thinking" layer.

Given the reference design's content-section slots and the product's Doc text,
Gemini decides which Doc material belongs in which design section, rewrites it
to fit, and proposes any extra sections the Doc needs. It returns a strict JSON
PLAN; the builder (agent6) applies that plan deterministically to the real
template, so the design can never be broken by the model.

The model is told to use ONLY facts from the Doc (no invention) and to emit HTML
fragments with the design's own CSS classes. Images are emitted as the marker
[[IMAGE]] and become placeholders in the page.

Uses the Gemini REST API with an API key (works server-side on Render). Set
GEMINI_API_KEY (or it falls back to GOOGLE_API_KEY). Enable the
"Generative Language API" on that key's Google Cloud project.
"""
from __future__ import annotations

import json
import re

import requests

from config import Config

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models/"
IMAGE_MARK = "[[IMAGE]]"


def _key() -> str:
    return (getattr(Config, "GEMINI_API_KEY", "") or Config.GOOGLE_API_KEY or "").strip()


def is_enabled() -> bool:
    return bool(getattr(Config, "AI_ENABLED", True)) and bool(_key())


# --------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------- #
_SYSTEM = """You are a meticulous web-content engineer. You fill a FIXED website \
template with a product's real content. You never change the design; you only \
decide which Doc content goes into which existing section, rewrite it to read \
cleanly, and propose extra sections when the Doc has material the template has \
no slot for.

HARD RULES
- Use ONLY facts found in the DOC. Never invent specs, numbers, grades, prices \
or claims. If the Doc lacks content for a non-furniture slot, set its action to \
"keep".
- Output HTML FRAGMENTS ONLY (no <html>/<body>), using exactly these classes:
    paragraphs      -> <p class="section-text">...</p>
    sub-headings    -> <h3 class="section-title section-title-h3">...</h3>
    tables          -> <div class="data-table-wrap"><table class="data-table">\
<thead>..</thead><tbody>..</tbody></table></div>
    bullet lists    -> <ul>...<li>...</li></ul>
    FAQ items       -> <div class="faq-item"><div class="faq-q" \
onclick="toggleFaq(this)">QUESTION<span class="faq-icon">+</span></div>\
<div class="faq-a">ANSWER</div></div>
- For any image use the literal marker [[IMAGE]] (it becomes a placeholder).
- Keep wording professional, concise and faithful to the Doc.
- "furniture" slots (Types, Applications, Shipping, Export, certifications, CTAs) \
must be left alone: do not return them in "sections".

Return STRICT JSON only, matching the schema you are given."""

_SCHEMA_HINT = """JSON shape:
{
  "h1": "the product H1 text",
  "intro": ["<p class=\\"pbmit-short-description\\"...>", "..."],   // lead paragraphs, plain text ok
  "sections": [
     {"id": "<slot id or heading>", "action": "replace"|"keep", "html": "<fragment>"}
  ],
  "extra": [
     {"title": "New Section Title", "html": "<fragment>"}        // Doc content with no slot
  ]
}"""


def _build_prompt(product: str, slots: list[dict], doc_text: str) -> str:
    slot_lines = []
    for s in slots:
        tag = "FURNITURE-KEEP" if s.get("furniture") else f"kind={s.get('kind','text')}"
        slot_lines.append(f'- id="{s["id"]}" | heading="{s["heading"]}" | {tag}')
    slots_block = "\n".join(slot_lines) or "(none)"
    return (
        f"{_SYSTEM}\n\n{_SCHEMA_HINT}\n\n"
        f"PRODUCT: {product}\n\n"
        f"TEMPLATE SECTION SLOTS (fill the non-furniture ones):\n{slots_block}\n\n"
        f"DOC CONTENT (the only source of truth):\n\"\"\"\n{doc_text}\n\"\"\"\n\n"
        "Now return the JSON plan."
    )


# --------------------------------------------------------------------- #
# Call
# --------------------------------------------------------------------- #
def _model() -> str:
    return getattr(Config, "AI_MODEL", "") or "gemini-2.0-flash"


def _extract_json(text: str):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def plan_page(product: str, slots: list[dict], doc_text: str,
              timeout: int = None) -> dict:
    """Returns the validated plan dict. Raises on any failure."""
    key = _key()
    if not key:
        raise RuntimeError("no AI key configured")
    timeout = timeout or int(getattr(Config, "AI_TIMEOUT", 60))
    url = f"{API_ROOT}{_model()}:generateContent?key={key}"
    payload = {
        "contents": [{"role": "user",
                      "parts": [{"text": _build_prompt(product, slots, doc_text)}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        },
    }
    r = requests.post(url, json=payload, timeout=timeout,
                      headers={"Content-Type": "application/json"})
    r.raise_for_status()
    data = r.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError(f"unexpected AI response: {json.dumps(data)[:300]}")
    plan = _extract_json(text)
    return _validate(plan)


def _validate(plan: dict) -> dict:
    if not isinstance(plan, dict):
        raise RuntimeError("AI plan is not an object")
    out = {"h1": str(plan.get("h1", "") or ""),
           "intro": [], "sections": [], "extra": []}
    for p in plan.get("intro", []) or []:
        if isinstance(p, str) and p.strip():
            out["intro"].append(p)
    for s in plan.get("sections", []) or []:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id", "") or "").strip()
        action = str(s.get("action", "keep") or "keep").strip().lower()
        if not sid:
            continue
        out["sections"].append({"id": sid,
                                "action": "replace" if action == "replace" else "keep",
                                "html": str(s.get("html", "") or "")})
    for e in plan.get("extra", []) or []:
        if not isinstance(e, dict):
            continue
        title = str(e.get("title", "") or "").strip()
        html = str(e.get("html", "") or "").strip()
        if title and html:
            out["extra"].append({"title": title, "html": html})
    return out
