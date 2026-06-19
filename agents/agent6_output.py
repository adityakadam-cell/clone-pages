"""
Agent 6 — Output & download.

Uses the reference HTML as a design SHELL and injects the Doc content:
  * the reference page's subject (its first banner <h1>) is replaced everywhere
    with the product title;
  * the main <article> is replaced with the Doc's sections, re-styled with the
    design's own content classes (.content-section / .section-title /
    .section-text / .data-table ...), so it matches the design;
  * the intro region (.*short-description) gets the Doc's lead-in paragraphs;
  * the sidebar, banner, header and footer are preserved.
Inline images become a placeholder; broken images swap to it.
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


def _cls(el):
    c = el.get("class")
    return " ".join(c) if c else ""


def _detect_vocab(scope):
    """Learn the design's content class names from the reference content area."""
    v = {"section": "", "title": "", "h3": "", "text": "",
         "table": "", "table_wrap": "", "divider": ""}
    h2 = scope.find("h2")
    if h2:
        v["title"] = _cls(h2)
        anc = h2.find_parent(lambda t: t.name in ("section", "div") and t.get("class"))
        if anc:
            v["section"] = _cls(anc)
        sib = h2.find_next_sibling()
        if sib and getattr(sib, "name", None) == "div" and "divider" in _cls(sib):
            v["divider"] = str(sib)
    h3 = scope.find("h3")
    if h3:
        v["h3"] = _cls(h3)
    p = scope.find("p", class_=True)
    if p:
        v["text"] = _cls(p)
    tbl = scope.find("table")
    if tbl:
        v["table"] = _cls(tbl)
        par = tbl.find_parent("div")
        if par and par.get("class"):
            v["table_wrap"] = _cls(par)
    return v


def _ca(name):
    return f' class="{name}"' if name else ""


def _doc_nodes(html):
    frag = BeautifulSoup(html or "", "lxml")
    root = frag.body or frag
    return [n for n in root.children
            if getattr(n, "name", None) or (isinstance(n, str) and n.strip())]


def _style_table(node, v):
    t = str(node)
    if v["table"]:
        t = re.sub(r"<table\b[^>]*>", f'<table class="{v["table"]}">', t, count=1)
    if v["table_wrap"]:
        t = f'<div class="{v["table_wrap"]}">{t}</div>'
    return t


def _style_sections(nodes, v):
    """Turn the doc's heading/paragraph/table flow into design content-sections."""
    sections, cur = [], {"title": None, "body": []}
    for n in nodes:
        nm = getattr(n, "name", None)
        if nm in ("h1", "h2"):
            if cur["title"] is not None or cur["body"]:
                sections.append(cur)
            cur = {"title": n.decode_contents(), "body": []}
        elif nm == "h3":
            cur["body"].append(f'<h3{_ca(v["h3"] or v["title"])}>{n.decode_contents()}</h3>')
        elif nm == "table":
            cur["body"].append(_style_table(n, v))
        elif nm == "p":
            cur["body"].append(f'<p{_ca(v["text"])}>{n.decode_contents()}</p>')
        elif nm:
            cur["body"].append(str(n))
    if cur["title"] is not None or cur["body"]:
        sections.append(cur)

    html = []
    for s in sections:
        inner = ""
        if s["title"] is not None:
            inner += f'<h2{_ca(v["title"])}>{s["title"]}</h2>{v["divider"]}'
        inner += "".join(s["body"])
        html.append(f'<section{_ca(v["section"])}>{inner}</section>')
    return "".join(html)


def _style_intro(nodes, intro_cls):
    """Lead-in paragraphs (before the first heading) for the intro region."""
    out = []
    for n in nodes:
        nm = getattr(n, "name", None)
        if nm == "p":
            out.append(f'<div{_ca(intro_cls)}>{n.decode_contents()}</div>')
        elif nm in ("ul", "ol"):
            out.append(str(n))
        elif nm:
            out.append(str(n))
    return "".join(out)


def _split_intro(nodes):
    """Return (intro_nodes_before_first_heading, section_nodes_from_first_heading)."""
    for i, n in enumerate(nodes):
        if getattr(n, "name", None) in ("h1", "h2"):
            return nodes[:i], nodes[i:]
    return nodes, []


def _set_inner(el, html, soup):
    el.clear()
    frag = BeautifulSoup(html, "lxml")
    for n in list((frag.body or frag).children):
        el.append(n)


def _inject(design, page):
    template_html = design.get("template_html", "") or ""
    soup = BeautifulSoup(template_html, "lxml")
    root = soup.body or soup
    new_title = (page.get("product") or page.get("meta_title") or "").strip()

    # 1. Title — banner H1, then replace the reference subject everywhere.
    h1 = root.find("h1")
    ref_title = h1.get_text(" ", strip=True) if h1 else ""
    if h1 and new_title:
        h1.clear()
        h1.append(NavigableString(new_title))
    if ref_title and new_title and ref_title != new_title:
        for tn in list(root.find_all(string=True)):
            if ref_title in tn:
                tn.replace_with(tn.replace(ref_title, new_title))

    # 2. Doc content -> intro + sections.
    content_html = page.get("content", "") or ""
    content_html = re.sub(r"^\s*<h1>.*?</h1>", "", content_html, count=1, flags=re.S | re.I)
    nodes = _doc_nodes(content_html)
    intro_nodes, section_nodes = _split_intro(nodes)

    article = root.find("article") or _content_fallback(root, h1)
    vocab = _detect_vocab(article) if article else {k: "" for k in
            ("section", "title", "h3", "text", "table", "table_wrap", "divider")}

    if article is not None:
        body_nodes = section_nodes or nodes
        _set_inner(article, _style_sections(body_nodes, vocab) or "<p></p>", soup)
        if section_nodes:           # only split intro out when there are sections
            intro_el = root.find(class_=re.compile("short-description"))
            holder = intro_el.parent if intro_el else None
            if holder is not None:
                intro_cls = _cls(intro_el)
                _set_inner(holder, _style_intro(intro_nodes, intro_cls)
                           or f'<div{_ca(intro_cls)}></div>', soup)
    else:
        sec = soup.new_tag("section"); sec["class"] = "api-agent-content"
        _set_inner(sec, _style_sections(nodes, vocab), soup)
        root.append(sec)

    body_html = root.decode_contents()
    return body_html.replace(IMAGE_MARK, PLACEHOLDER_IMG)


def _content_fallback(root, h1):
    best, best_len = None, 0
    for el in root.find_all(["main", "section", "div"]):
        if el.name in ("nav", "header", "footer"):
            continue
        if el.find(["nav", "header", "footer", "aside"]):
            continue
        if h1 and (el is h1 or h1 in el.descendants):
            continue
        text = el.get_text(" ", strip=True)
        if len(text) >= 120 and len(text) > best_len:
            best, best_len = el, len(text)
    return best


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
