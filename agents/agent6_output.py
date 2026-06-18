"""
Agent 6 — Output & download.

Build each approved page into a standalone HTML file:
  * Design (CSS + JS) captured from the provided HTML in Agent 2.
  * Content fetched from that row's Doc (Agent 3), formatted into paragraphs.
  * Inline-image markers ([[IMAGE]]) become a placeholder image, and a small
    script swaps ANY broken image on the page to the same placeholder.
Then offer single + bulk (zip) downloads.
"""
import re
import zipfile
from html import escape

from config import Config
from core.utils import ok, fail, slugify
from core.doc_fetcher import IMAGE_MARK

# Self-contained SVG placeholder (no external dependency).
PLACEHOLDER_SRC = (
    "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmci"
    "IHdpZHRoPSI2NDAiIGhlaWdodD0iMzYwIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAl"
    "IiBmaWxsPSIjZTJlOGYwIi8+PHJlY3QgeD0iOCIgeT0iOCIgd2lkdGg9IjYyNCIgaGVpZ2h0PSIz"
    "NDQiIGZpbGw9Im5vbmUiIHN0cm9rZT0iIzk0YTNiOCIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2Ut"
    "ZGFzaGFycmF5PSIxMCA4Ii8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlh"
    "bCxzYW5zLXNlcmlmIiBmb250LXNpemU9IjMwIiBmaWxsPSIjNjQ3NDhiIiB0ZXh0LWFuY2hvcj0i"
    "bWlkZGxlIiBkb21pbmFudC1iYXNlbGluZT0ibWlkZGxlIj5JbWFnZSBwbGFjZWhvbGRlcjwvdGV4"
    "dD48L3N2Zz4="
)
PLACEHOLDER_IMG = (f'<img class="api-img-placeholder" alt="image placeholder" '
                   f'src="{PLACEHOLDER_SRC}">')

# Replaces any image that fails to load (design or content) with the placeholder.
IMG_FALLBACK_SCRIPT = (
    "<script>(function(){var P='" + PLACEHOLDER_SRC + "';"
    "function fix(i){if(i.src!==P){i.src=P;i.classList.add('api-img-placeholder');}}"
    "document.addEventListener('DOMContentLoaded',function(){"
    "document.querySelectorAll('img').forEach(function(i){"
    "i.addEventListener('error',function(){fix(i);});"
    "if(i.complete&&i.naturalWidth===0){fix(i);}});});})();</script>"
)

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{meta_title}</title>
  <meta name="description" content="{meta_description}">
{css_block}
</head>
<body>
{template_html}
<main class="api-agent-content">
{content}
</main>
{js_block}
{img_fallback}
</body>
</html>
"""

_HTML_TAG = re.compile(r"<(p|div|h[1-6]|ul|ol|li|section|article|table|img|br)\b", re.I)


def _design(state):
    return state.get("agent2", {}) or {}


def _css_block(design):
    out = [f'  <link rel="stylesheet" href="{escape(h)}">'
           for h in design.get("css_links", [])]
    for css in design.get("inline_css", []):
        if css and css.strip():
            out.append(f"  <style>{css}</style>")
    return "\n".join(out)


def _js_block(design, template_html=""):
    out = [f'  <script src="{escape(s)}"></script>'
           for s in design.get("js_links", [])]
    for js in design.get("inline_js", []):
        if js and js.strip() and js.strip() not in (template_html or ""):
            out.append(f"  <script>{js}</script>")
    return "\n".join(out)


def _format_content(content: str) -> str:
    """Doc text -> HTML. [[IMAGE]] markers become placeholders; plain text
    becomes paragraphs; existing HTML is kept as-is."""
    content = content or ""
    if _HTML_TAG.search(content):
        return content

    html, first = [], True
    # split on the image marker so placeholders land where images were
    for part in content.split(IMAGE_MARK):
        for b in re.split(r"\n\s*\n", part):
            lines = [escape(ln.strip()) for ln in b.splitlines() if ln.strip()]
            if not lines:
                continue
            if first and len(lines) == 1 and len(lines[0]) < 90:
                html.append(f"<h1>{lines[0]}</h1>")
            else:
                html.append("<p>" + "<br>".join(lines) + "</p>")
            first = False
        html.append(PLACEHOLDER_IMG)
    if html and html[-1] == PLACEHOLDER_IMG:    # no trailing marker -> drop extra
        html.pop()
    return "\n".join(html)


def _approved_pages(state):
    a7 = state.get("agent7", {})
    if a7.get("approved"):
        return a7["approved"]
    a5 = state.get("agent5", {})
    return a5.get("pages") or state.get("agent3", {}).get("pages", [])


def build(state):
    pages = _approved_pages(state)
    if not pages:
        return fail("No approved pages to build.")

    design = _design(state)
    template_html = design.get("template_html", "")
    css_block = _css_block(design)
    js_block = _js_block(design, template_html)

    built = []
    for p in pages:
        slug = p.get("slug") or slugify(p.get("product", "page"))
        filename = f"{slug}.html"
        html = PAGE_TEMPLATE.format(
            meta_title=escape(p.get("meta_title", "")),
            meta_description=escape(p.get("meta_description", "")),
            css_block=css_block,
            template_html=template_html,
            content=_format_content(p.get("content", "")),
            js_block=js_block,
            img_fallback=IMG_FALLBACK_SCRIPT,
        )
        (Config.OUTPUT_DIR / filename).write_text(html, encoding="utf-8")
        built.append({"product": p.get("product", ""), "filename": filename})

    return ok({"built": built, "count": len(built)},
              f"Built {len(built)} page(s).")


def zip_pages(filenames):
    if not filenames:
        return fail("Select at least one page to zip.")
    zip_name = "api-agent-pages.zip"
    zip_path = Config.OUTPUT_DIR / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in filenames:
            fp = Config.OUTPUT_DIR / name
            if fp.exists():
                zf.write(fp, arcname=name)
    return ok({"zip": zip_name}, f"Zipped {len(filenames)} page(s).")
