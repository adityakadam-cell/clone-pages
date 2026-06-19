"""
Agent 6 — Output & download.

Reference HTML = design SHELL; the Doc content is injected into it:
  * banner <h1> subject -> product title (everywhere);
  * the design's MAIN content COLUMN (any layout: <article>/<main>/largest
    block) is replaced with the Doc's sections, re-styled with the design's
    content classes (.content-section/.section-title/.section-text/.data-table);
  * SPECIAL sections are rebuilt into the design's own components when detected:
      - "FAQ"             -> .faq-item / .faq-q / .faq-a accordion (+ toggle JS);
      - "...Applications" -> .card-app-card grid;
      - "Types/Forms..."  -> .form-card grid;
  * intro region (.*short-description / lead / intro) gets the Doc's lead-in;
  * header, nav, footer and sidebar are ALWAYS preserved; any other body
    section the Doc has no content for is removed (fully automatic).
Inline images -> placeholder; broken images swap to it.
"""
import re
import zipfile
from collections import Counter
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


def _find_cls(root, pattern):
    return root.find(class_=re.compile(pattern)) if root else None


def _detect_vocab(scope):
    v = {"section": "", "title": "", "h3": "", "text": "",
         "table": "", "table_wrap": "", "divider": ""}
    if scope is None:
        return v
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


def _detect_special(root):
    sp = {"faq": None, "app": None, "form": None}
    item = _find_cls(root, r"\bfaq-item\b")
    if item:
        q = _find_cls(item, r"faq-q")
        a = _find_cls(item, r"faq-a")
        icon = _find_cls(item, r"faq-icon")
        sp["faq"] = {"item": _cls(item), "q": _cls(q) if q else "faq-q",
                     "a": _cls(a) if a else "faq-a",
                     "icon": _cls(icon) if icon else "faq-icon",
                     "onclick": (q.get("onclick") if q else "") or "toggleFaq(this)",
                     "icon_txt": (icon.get_text() if icon else "+") or "+"}
    card = _find_cls(root, r"card-app-card")
    if card:
        grid = card.find_parent(class_=re.compile(r"card-app-grid"))
        sp["app"] = {"grid": _cls(grid) if grid else "card-app-grid",
                     "card": _cls(card),
                     "top": _cls(_find_cls(card, r"card-app-top") or card) or "card-app-top",
                     "icon": _cls(_find_cls(card, r"card-app-icon")) or "card-app-icon",
                     "icon_txt": (_find_cls(card, r"card-app-icon").get_text()
                                  if _find_cls(card, r"card-app-icon") else "◆"),
                     "title": _cls(_find_cls(card, r"card-app-title")) or "card-app-title",
                     "text": _cls(_find_cls(card, r"card-app-text")) or "card-app-text"}
    fcard = _find_cls(root, r"\bform-card\b")
    if fcard:
        grid = fcard.find_parent(class_=re.compile(r"form-cards-grid"))
        sp["form"] = {"grid": _cls(grid) if grid else "row g-4 form-cards-grid",
                      "col": "col-md-4", "card": _cls(fcard),
                      "media": _cls(_find_cls(fcard, r"form-card-media")) or "form-card-media",
                      "body": _cls(_find_cls(fcard, r"form-card-body")) or "form-card-body",
                      "title": _cls(_find_cls(fcard, r"form-card-title")) or "form-card-title"}
    return sp


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


def _heading_level(name):
    return int(name[1]) if name and re.match(r"h[1-6]$", name) else 0


def _section_level(nodes):
    levels = [_heading_level(getattr(n, "name", "")) for n in nodes]
    levels = [l for l in levels if l]
    if not levels:
        return 2
    counts = Counter(levels)
    repeated = [l for l in sorted(counts) if counts[l] >= 2]
    return repeated[0] if repeated else min(levels)


def _pairs(nodes):
    """Pair each heading with the paragraphs that follow it -> [(title, body_html)]."""
    out, title, body = [], None, []
    for n in nodes:
        if _heading_level(getattr(n, "name", "")):
            if title is not None:
                out.append((title, "".join(body)))
            title, body = n.decode_contents(), []
        elif getattr(n, "name", None):
            body.append(str(n) if n.name != "p" else f"<p>{n.decode_contents()}</p>")
    if title is not None:
        out.append((title, "".join(body)))
    return out


def _render_faq(nodes, faq):
    items = []
    for q, a in _pairs(nodes):
        items.append(
            f'<div class="{faq["item"]}"><div class="{faq["q"]}" onclick="{faq["onclick"]}">'
            f'{q}<span class="{faq["icon"]}">{faq["icon_txt"]}</span></div>'
            f'<div class="{faq["a"]}">{a}</div></div>')
    return "".join(items)


def _render_app_cards(nodes, app):
    cards = []
    for title, body in _pairs(nodes):
        txt = re.sub(r"</?p>", " ", body).strip()
        cards.append(
            f'<article class="{app["card"]}"><div class="{app["top"]}">'
            f'<span class="{app["icon"]}">{app["icon_txt"]}</span>'
            f'<h3 class="{app["title"]}">{title}</h3></div>'
            f'<p class="{app["text"]}">{txt}</p></article>')
    return f'<div class="{app["grid"]}">{"".join(cards)}</div>' if cards else ""


def _render_form_cards(nodes, form):
    titles = []
    for n in nodes:
        if _heading_level(getattr(n, "name", "")):
            titles.append(n.decode_contents())
        elif getattr(n, "name", None) in ("ul", "ol"):
            titles += [li.decode_contents() for li in n.find_all("li")]
    cards = [
        f'<div class="{form["col"]}"><div class="{form["card"]}">'
        f'<div class="{form["media"]}">{PLACEHOLDER_IMG}</div>'
        f'<div class="{form["body"]}"><h3 class="{form["title"]}">{t}</h3></div></div></div>'
        for t in titles]
    return f'<div class="{form["grid"]}">{"".join(cards)}</div>' if cards else ""


def _render_body(nodes, v):
    out = []
    for n in nodes:
        nm = getattr(n, "name", None)
        if _heading_level(nm):
            out.append(f'<h3{_ca(v["h3"] or v["title"])}>{n.decode_contents()}</h3>')
        elif nm == "table":
            out.append(_style_table(n, v))
        elif nm == "p":
            out.append(f'<p{_ca(v["text"])}>{n.decode_contents()}</p>')
        elif nm:
            out.append(str(n))
    return "".join(out)


def _style_sections(nodes, v, special):
    sec_lvl = _section_level(nodes)
    groups, cur = [], {"title": None, "ttext": "", "nodes": []}
    for n in nodes:
        lvl = _heading_level(getattr(n, "name", ""))
        if lvl and lvl <= sec_lvl:
            if cur["title"] is not None or cur["nodes"]:
                groups.append(cur)
            cur = {"title": n.decode_contents(),
                   "ttext": n.get_text(" ", strip=True).lower(), "nodes": []}
        else:
            cur["nodes"].append(n)
    if cur["title"] is not None or cur["nodes"]:
        groups.append(cur)

    html = []
    for g in groups:
        t = g["ttext"]
        if special.get("faq") and ("faq" in t or "frequently asked" in t):
            body = _render_faq(g["nodes"], special["faq"]) or _render_body(g["nodes"], v)
        elif special.get("app") and "application" in t:
            body = _render_app_cards(g["nodes"], special["app"]) or _render_body(g["nodes"], v)
        elif special.get("form") and re.search(r"\b(types?|forms?|shapes?)\b", t):
            body = _render_form_cards(g["nodes"], special["form"]) or _render_body(g["nodes"], v)
        else:
            body = _render_body(g["nodes"], v)
        inner = ""
        if g["title"] is not None:
            inner += f'<h2{_ca(v["title"])}>{g["title"]}</h2>{v["divider"]}'
        inner += body
        html.append(f'<section{_ca(v["section"])}>{inner}</section>')
    return "".join(html)


def _style_intro(nodes, intro_cls):
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
    sec_lvl = _section_level(nodes)
    for i, n in enumerate(nodes):
        if _heading_level(getattr(n, "name", "")) and _heading_level(n.name) <= sec_lvl:
            return nodes[:i], nodes[i:]
    return nodes, []


def _set_inner(el, html):
    el.clear()
    frag = BeautifulSoup(html, "lxml")
    for n in list((frag.body or frag).children):
        el.append(n)


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


def _main_region(root, h1):
    """Find the design's main content COLUMN for ANY layout. Trust the
    semantic landmarks first (a sparse template may have little placeholder
    text, so length is NOT required for <article>/<main>):
      1. <article> that holds real content and isn't inside chrome;
      2. <main>, narrowed away from any sidebar/aside it contains;
      3. largest non-chrome text block (fallback heuristic)."""
    art = root.find("article")
    if (art is not None
            and not art.find_parent(["header", "nav", "footer"])
            and art.find(["h1", "h2", "h3", "h4", "p", "table", "ul", "ol"])):
        return art

    main = root.find("main")
    if main is not None and not main.find_parent(["header", "nav", "footer"]):
        aside = main.find("aside") or main.find(class_=re.compile(r"sidebar|side-bar"))
        if aside is not None:
            best, best_len = None, 0
            for el in main.find_all(["article", "section", "div"]):
                if el is aside or aside in el.descendants:
                    continue
                if el.find(["aside"]) or el.find(class_=re.compile(r"sidebar|side-bar")):
                    continue
                t = len(el.get_text(" ", strip=True))
                if t > best_len:
                    best, best_len = el, t
            if best is not None and best_len > 0:
                return best
        return main

    return _content_fallback(root, h1)


_CHROME_RE = re.compile(
    r"(header|nav(bar)?|footer|sidebar|side-bar|aside|widget|rail|breadcrumb|"
    r"banner|hero|menu|topbar|top-bar|cookie|newsletter|subscribe|enquiry|"
    r"quote|contact|logo|search)", re.I)


def _is_chrome(el):
    """True for header/nav/footer/sidebar/banner-type blocks that must survive
    regardless of the Doc content."""
    if getattr(el, "name", None) in ("header", "nav", "footer", "aside"):
        return True
    if el.find_parent(["header", "nav", "footer", "aside"]):
        return True
    if _CHROME_RE.search(" ".join(el.get("class") or [])):
        return True
    if el.find(["header", "nav", "footer"]):
        return True
    return False


def _strip_unmatched(root, main_el):
    """Remove body sections not backed by Doc content. All Doc content lives
    inside main_el, so any sibling block along main_el's ancestor chain that
    isn't chrome (header/nav/footer/sidebar/banner) is design-only -> drop it.
    Header, footer, nav and sidebar are always kept."""
    if main_el is None:
        return
    node, guard = main_el, 0
    while node is not None and getattr(node, "name", None) != "body" and guard < 40:
        guard += 1
        parent = node.parent
        if parent is None:
            break
        for sib in list(node.find_next_siblings()) + list(node.find_previous_siblings()):
            if getattr(sib, "name", None) is None:
                continue
            if sib is main_el or main_el in sib.descendants:
                continue
            if _is_chrome(sib):
                continue
            sib.decompose()
        node = parent


def _inject(design, page):
    template_html = design.get("template_html", "") or ""
    soup = BeautifulSoup(template_html, "lxml")
    root = soup.body or soup
    new_title = (page.get("product") or page.get("meta_title") or "").strip()

    special = _detect_special(root)

    h1 = root.find("h1")
    ref_title = h1.get_text(" ", strip=True) if h1 else ""
    if h1 and new_title:
        h1.clear()
        h1.append(NavigableString(new_title))
    if ref_title and new_title and ref_title != new_title:
        for tn in list(root.find_all(string=True)):
            if ref_title in tn:
                tn.replace_with(tn.replace(ref_title, new_title))

    content_html = page.get("content", "") or ""
    content_html = re.sub(r"^\s*<h1>.*?</h1>", "", content_html, count=1, flags=re.S | re.I)
    nodes = _doc_nodes(content_html)
    intro_nodes, section_nodes = _split_intro(nodes)

    article = _main_region(root, h1)
    vocab = _detect_vocab(article)

    if article is not None:
        intro_el = root.find(
            class_=re.compile(r"short-description|lead-?in|intro|excerpt|summary"))
        holder = intro_el.parent if intro_el else None
        # Only split the intro into its own region when that region is SEPARATE
        # from the main content column (otherwise we'd overwrite what we inject).
        sep_intro = (bool(section_nodes) and holder is not None
                     and holder is not article
                     and article not in holder.descendants
                     and holder not in article.descendants)
        if sep_intro:
            _set_inner(article, _style_sections(section_nodes, vocab, special) or "<p></p>")
            intro_cls = _cls(intro_el)
            _set_inner(holder, _style_intro(intro_nodes, intro_cls)
                       or f'<div{_ca(intro_cls)}></div>')
        else:
            _set_inner(article, _style_sections(nodes, vocab, special) or "<p></p>")
        _strip_unmatched(root, article)
    else:
        sec = soup.new_tag("section")
        sec["class"] = "api-agent-content"
        _set_inner(sec, _style_sections(nodes, vocab, special))
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
