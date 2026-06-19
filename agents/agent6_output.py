"""
Agent 6 — Output & download.

Builds each page by using the reference HTML as a DESIGN SHELL and injecting the
Doc content into it (auto-detect):
  * the reference page's subject (its first <h1> text) is replaced everywhere
    with the product title;
  * the main content container is replaced with the Doc's structured HTML
    (headings, paragraphs, tables, lists) in the same design;
  * inline images become a placeholder, and any broken image swaps to it.
"""
import re
import zipfile
from html import escape

from bs4 import BeautifulSoup, NavigableString

from config import Config
from core.utils import ok, fail, slugify
from core.doc_fetcher import IMAGE_MARK

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
{body_html}
{js_block}
{img_fallback}
</body>
</html>
"""


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


def _find_content_container(root, hero_h1):
    """Pick the block that holds the page body text: most text, but not a
    nav/header/footer region and not the hero (the element with the H1)."""
    hero_ancestors = set(id(a) for a in (hero_h1.parents if hero_h1 else []))
    best, best_len = None, 0
    for el in root.find_all(["main", "article", "section", "div"]):
        if el.name in ("nav", "header", "footer"):
            continue
        if el.find(["nav", "header", "footer"]):
            continue
        if hero_h1 and (el is hero_h1 or hero_h1 in el.descendants):
            continue
        if id(el) in hero_ancestors:
            continue
        text = el.get_text(" ", strip=True)
        if len(text) >= 120 and len(text) > best_len:
            best, best_len = el, len(text)
    return best


def _inject(design, page):
    """Return the modified design body (string) with title + content swapped."""
    template_html = design.get("template_html", "") or ""
    soup = BeautifulSoup(template_html, "lxml")
    root = soup.body or soup

    new_title = (page.get("product") or page.get("meta_title") or "").strip()

    # 1. Title: set the first <h1>, then replace the reference subject elsewhere.
    h1 = root.find("h1")
    ref_title = h1.get_text(" ", strip=True) if h1 else ""
    if h1 and new_title:
        h1.clear()
        h1.append(NavigableString(new_title))
    if ref_title and new_title and ref_title != new_title:
        for tn in list(root.find_all(string=True)):
            if ref_title in tn:
                tn.replace_with(tn.replace(ref_title, new_title))

    # 2. Content: drop the doc's own leading title (the hero already shows it),
    #    then inject into the main content container.
    content_html = page.get("content", "") or ""
    content_html = re.sub(r"^\s*<h1>.*?</h1>", "", content_html, count=1,
                          flags=re.S | re.I)
    frag = BeautifulSoup(content_html, "lxml")
    frag_root = frag.body or frag
    nodes = [n for n in list(frag_root.children)]

    container = _find_content_container(root, h1)
    if container is not None and nodes:
        container.clear()
        for n in nodes:
            container.append(n)
    elif nodes:                       # no container found -> append a section
        sec = soup.new_tag("section")
        sec["class"] = "api-agent-content"
        for n in nodes:
            sec.append(n)
        root.append(sec)

    body_html = root.decode_contents()
    return body_html.replace(IMAGE_MARK, PLACEHOLDER_IMG)


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
            body_html=_inject(design, p),
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
