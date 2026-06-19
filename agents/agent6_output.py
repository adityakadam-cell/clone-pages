"""
Agent 6 — Output & download.  TEMPLATE-FILL builder ("self thinker").

The reference page is kept 100% intact (header, nav, banner, badges, featured
image, the "page consists of" list, sidebar, Export Worldwide, Shipping,
certifications, CTAs, footer). Only what changes per product is swapped in:

  1. the <h1> and every "Stainless Steel Pipe(s)" mention -> the new product
     name (chrome menus / sidebar / footer are left alone);
  2. the .pbmit-short-description intro paragraphs -> the Doc's lead-in;
  3. each .content-section the Doc actually covers (Specifications, Price,
     Grades, Comparison, FAQ, ...) has ONLY its body replaced with the Doc's
     matching section, re-styled with the design's own classes. The heading,
     divider and section wrapper are preserved.

Standard template furniture the Doc has no content for (Types image cards,
Applications icon cards, Shipping panel, Export Worldwide tabs, certifications,
CTA bands) is kept exactly as in the design.  Doc sections with no slot in the
template (e.g. Chemical Composition, Mechanical Properties) are appended as new
.content-sections in the same design style, just before the FAQ.
"""
import re
import zipfile
from collections import Counter
from html import escape

from bs4 import BeautifulSoup, NavigableString

from config import Config
from core.utils import ok, fail, slugify
from core.doc_fetcher import IMAGE_MARK
from core import ai_writer as _AI

import logging
log = logging.getLogger("api-agent.agent6")

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

# Topics that are standard furniture across every page -> keep the design's
# version, never overwrite from the Doc and never append the Doc's copy.
FURNITURE = {"types", "applications", "shipping", "export"}


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


def _ca(name):
    return f' class="{name}"' if name else ""


def _set_inner(el, html):
    el.clear()
    frag = BeautifulSoup(html, "lxml")
    for n in list((frag.body or frag).children):
        el.append(n)


def _doc_nodes(html):
    frag = BeautifulSoup(html or "", "lxml")
    root = frag.body or frag
    return [n for n in root.children
            if getattr(n, "name", None) or (isinstance(n, str) and n.strip())]


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
    """Pair each heading with following paragraphs -> [(title_html, body_html)]."""
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


# ---------------------------------------------------------------------- #
# Doc -> sections
# ---------------------------------------------------------------------- #
def _section_groups(nodes):
    """Group nodes at their shallowest repeated heading level ->
    (lead_nodes, [ {title, ttext, nodes}, ... ])."""
    sec_lvl = _section_level(nodes)
    lead, groups, cur = [], [], None
    for n in nodes:
        lvl = _heading_level(getattr(n, "name", ""))
        if lvl and lvl <= sec_lvl:
            if cur is not None:
                groups.append(cur)
            cur = {"title": n.decode_contents(),
                   "ttext": n.get_text(" ", strip=True), "nodes": []}
        elif cur is None:
            lead.append(n)
        else:
            cur["nodes"].append(n)
    if cur is not None:
        groups.append(cur)
    return lead, groups


def _doc_sections(html):
    """Split Doc HTML into (intro_nodes, [section groups]).

    The Doc usually opens with a TITLE heading (the product name) whose body is
    the intro and which may nest the first real sub-sections under it. Unwrap
    that title: its lead paragraphs feed the intro, its nested sub-sections are
    re-grouped so they match template slots (e.g. Sizes) instead of leaking in
    as one stray block."""
    intro, groups = _section_groups(_doc_nodes(html))
    if groups and _topic(groups[0]["ttext"]) is None:
        first = groups.pop(0)
        sub_lead, sub_groups = _section_groups(first["nodes"])
        intro = intro + sub_lead
        groups = sub_groups + groups
    return intro, groups


def _topic(text):
    t = (text or "").lower()
    if "frequently asked" in t or re.search(r"\bfaqs?\b", t):
        return "faq"
    if "export" in t and ("worldwide" in t or "countr" in t or "global" in t):
        return "export"
    if "shipping" in t or "packaging" in t or "packing" in t:
        return "shipping"
    if "application" in t or "industr" in t:
        return "applications"
    if re.search(r"\bvs\b|\bversus\b|comparison|difference", t):
        return "comparison"
    if re.search(r"\btypes?\b|\bforms?\b|\bshapes?\b", t):
        return "types"
    if "price" in t or "pricing" in t or "cost" in t:
        return "price"
    if "chemical" in t or "composition" in t:
        return "composition"
    if "mechanical" in t or "physical propert" in t:
        return "mechanical"
    if "specification" in t or re.search(r"\bspecs?\b", t):
        return "specs"
    if "size" in t or "dimension" in t:
        return "sizes"
    if "grade" in t:
        return "grades"
    return None


# ---------------------------------------------------------------------- #
# Rendering with the design's classes
# ---------------------------------------------------------------------- #
def _style_table(node):
    t = re.sub(r"<table\b[^>]*>", '<table class="data-table">', str(node), count=1)
    return f'<div class="data-table-wrap">{t}</div>'


def _render_section_body(nodes):
    out = []
    for n in nodes:
        nm = getattr(n, "name", None)
        if nm is None:
            continue
        if _heading_level(nm):
            out.append(f'<h3 class="section-title section-title-h3">{n.decode_contents()}</h3>')
        elif nm == "table":
            out.append(_style_table(n))
        elif nm == "p":
            out.append(f'<p class="section-text">{n.decode_contents()}</p>')
        else:
            out.append(str(n))
    return "".join(out)


def _faq_vocab(root):
    item = _find_cls(root, r"\bfaq-item\b")
    if not item:
        return {"item": "faq-item", "q": "faq-q", "a": "faq-a",
                "icon": "faq-icon", "onclick": "toggleFaq(this)", "icon_txt": "+"}
    q = _find_cls(item, r"faq-q")
    a = _find_cls(item, r"faq-a")
    icon = _find_cls(item, r"faq-icon")
    return {"item": _cls(item), "q": _cls(q) if q else "faq-q",
            "a": _cls(a) if a else "faq-a", "icon": _cls(icon) if icon else "faq-icon",
            "onclick": (q.get("onclick") if q else "") or "toggleFaq(this)",
            "icon_txt": (icon.get_text() if icon else "+") or "+"}


def _render_faq(nodes, fq):
    out = []
    for q, a in _pairs(nodes):
        out.append(
            f'<div class="{fq["item"]}"><div class="{fq["q"]}" onclick="{fq["onclick"]}">'
            f'{q}<span class="{fq["icon"]}">{fq["icon_txt"]}</span></div>'
            f'<div class="{fq["a"]}">{a}</div></div>')
    return "".join(out)


def _title_html(text):
    text = (text or "").strip()
    if not text:
        return ""
    parts = text.rsplit(" ", 1)
    if len(parts) == 2:
        return f"{escape(parts[0])} <span>{escape(parts[1])}</span>"
    return f"<span>{escape(text)}</span>"


# ---------------------------------------------------------------------- #
# Product rename (skips header / nav / footer / sidebar menus)
# ---------------------------------------------------------------------- #
_CHROME_ANCESTOR = re.compile(
    r"site-header|site-footer|pbmit-footer|navigation|navbar|pbmit-mega|"
    r"sub-menu|side-nav|toc-sidebar|pbmit-header|widget", re.I)


def _in_chrome(tn):
    p = tn.parent
    while p is not None and getattr(p, "name", None):
        if p.name in ("header", "nav", "footer", "aside", "script", "style"):
            return True
        if _CHROME_ANCESTOR.search(" ".join(p.get("class") or [])):
            return True
        p = p.parent
    return False


def _rename_product(root, ref_title, new_title, h1):
    if not new_title:
        return
    ref_core = re.sub(r"s$", "", (ref_title or "").strip())
    if ref_core and ref_core.lower() != new_title.lower():
        ref_plur = ref_core + "s"
        new_plur = new_title + "s"
        pat_plur = re.compile(re.escape(ref_plur), re.I)
        pat_sing = re.compile(re.escape(ref_core), re.I)
        for tn in list(root.find_all(string=True)):
            s = str(tn)
            if ref_core.lower() not in s.lower():
                continue
            if _in_chrome(tn):
                continue
            s2 = pat_sing.sub(new_title, pat_plur.sub(new_plur, s))
            if s2 != s:
                tn.replace_with(s2)
    if h1 is not None:
        _set_inner(h1, _title_html(new_title))


# ---------------------------------------------------------------------- #
# Intro + section swapping
# ---------------------------------------------------------------------- #
def _swap_intro(root, intro_nodes):
    descs = root.find_all(class_="pbmit-short-description")
    if not descs or not intro_nodes:
        return
    keep = None
    for d in descs:
        if "page consists" in d.get_text(" ", strip=True).lower():
            keep = d
            break
    html = ""
    for n in intro_nodes:
        nm = getattr(n, "name", None)
        if nm == "p":
            html += f'<div class="pbmit-short-description">{n.decode_contents()}</div>'
        elif nm in ("ul", "ol"):
            html += str(n)
    if not html:
        return
    frag = BeautifulSoup(html, "lxml")
    new_nodes = list((frag.body or frag).children)
    anchor = keep or descs[0]
    for nn in new_nodes:
        anchor.insert_before(nn)
    for d in descs:
        if d is not keep:
            d.decompose()


def _replace_section_body(sec, body_html):
    """Keep the section's heading + divider; replace everything else."""
    title = sec.find(["h2", "h3"], class_=re.compile("section-title"))
    divider = sec.find("div", class_=re.compile("section-divider"))
    keep_ids = {id(x) for x in (title, divider) if x is not None}
    for child in list(sec.children):
        if getattr(child, "name", None) is None:
            if not str(child).strip():
                child.extract()
            continue
        if id(child) not in keep_ids:
            child.decompose()
    frag = BeautifulSoup(body_html, "lxml")
    for n in list((frag.body or frag).children):
        sec.append(n)


def _content_sections(article):
    return [s for s in article.find_all("section")
            if "content-section" in (s.get("class") or [])]


def _swap_sections(root, article, doc_groups, faq_vocab):
    used = set()
    by_topic = {}
    for i, g in enumerate(doc_groups):
        by_topic.setdefault(_topic(g["ttext"]), []).append(i)

    for sec in _content_sections(article):
        h = sec.find(["h2", "h3"], class_=re.compile("section-title"))
        if h is None:
            continue                                  # CTA bands etc. -> keep
        topic = _topic(h.get_text(" ", strip=True))
        if topic is None or topic in FURNITURE:
            continue                                  # furniture / unknown -> keep
        free = [i for i in by_topic.get(topic, []) if i not in used]
        if not free:
            continue                                  # no Doc content -> keep template
        gi = free[0]
        used.add(gi)
        nodes = doc_groups[gi]["nodes"]
        body = (_render_faq(nodes, faq_vocab) if topic == "faq"
                else _render_section_body(nodes))
        if body.strip():
            _replace_section_body(sec, body)

    # Append Doc sections with no template slot (real content, not furniture).
    extra = ""
    for i, g in enumerate(doc_groups):
        if i in used:
            continue
        tp = _topic(g["ttext"])
        if tp in FURNITURE:
            continue
        body = _render_section_body(g["nodes"])
        if not body.strip():
            continue
        extra += (f'<section class="content-section">'
                  f'<h2 class="section-title">{_title_html(g["ttext"])}</h2>'
                  f'<div class="section-divider"></div>{body}</section>')
    if extra:
        frag = BeautifulSoup(extra, "lxml")
        new_secs = list((frag.body or frag).children)
        faq_sec = next((s for s in _content_sections(article)
                        if s.find(["h2", "h3"], class_=re.compile("section-title"))
                        and _topic(s.find(["h2", "h3"],
                                   class_=re.compile("section-title"))
                                   .get_text(" ", strip=True)) == "faq"), None)
        ctas = [s for s in article.find_all("section")
                if "cta-section" in (s.get("class") or [])]
        anchor = faq_sec or (ctas[-1] if ctas else None)
        if anchor is not None:
            for ns in new_secs:
                anchor.insert_before(ns)
        else:
            for ns in new_secs:
                article.append(ns)


# ---------------------------------------------------------------------- #
# Fallback main-region finder (designs without <article class="main-content">)
# ---------------------------------------------------------------------- #
def _content_fallback(root, h1):
    best, best_len = None, 0
    for el in root.find_all(["main", "article", "section", "div"]):
        if el.name in ("nav", "header", "footer"):
            continue
        if el.find(["nav", "header", "footer"]):
            continue
        if h1 and (el is h1 or h1 in el.descendants):
            continue
        text = el.get_text(" ", strip=True)
        if len(text) >= 120 and len(text) > best_len:
            best, best_len = el, len(text)
    return best


def _main_region(root, h1):
    art = root.find("article", class_="main-content")
    if art is not None:
        return art
    art = root.find("article")
    if art is not None and art.find("section"):
        return art
    main = root.find("main")
    if main is not None and main.find("section"):
        return main
    return _content_fallback(root, h1)


# ---------------------------------------------------------------------- #
# Orchestration
# ---------------------------------------------------------------------- #
def _inject(design, page):
    template_html = design.get("template_html", "") or ""
    soup = BeautifulSoup(template_html, "lxml")
    root = soup.body or soup
    new_title = (page.get("product") or page.get("meta_title") or "").strip()

    h1 = root.find("h1")
    ref_title = h1.get_text(" ", strip=True) if h1 else ""
    _rename_product(root, ref_title, new_title, h1)

    content_html = page.get("content", "") or ""
    content_html = re.sub(r"^\s*<h1>.*?</h1>", "", content_html, count=1, flags=re.S | re.I)

    article = _main_region(root, h1)
    if article is not None:
        slots = _design_slots(article) if _content_sections(article) else []
        used_ai = False
        if slots and _AI.is_enabled():
            try:
                plan = _AI.plan_page(new_title, slots, _doc_to_md(content_html))
                _apply_plan(root, article, plan)
                used_ai = True
                log.info("AI builder filled '%s'", new_title or "page")
            except Exception as exc:                       # pragma: no cover
                log.warning("AI builder failed (%s); using rule-based fill", exc)
        if not used_ai:
            intro_nodes, doc_groups = _doc_sections(content_html)
            _swap_intro(root, intro_nodes)
            if slots:
                _swap_sections(root, article, doc_groups, _faq_vocab(root))
            else:
                body = "".join(
                    f'<section class="content-section">'
                    f'<h2 class="section-title">{_title_html(g["ttext"])}</h2>'
                    f'<div class="section-divider"></div>'
                    f'{_render_section_body(g["nodes"])}</section>'
                    for g in doc_groups)
                _set_inner(article, body or "<p></p>")

    _placeholder_images(root)
    body_html = root.decode_contents()
    return body_html.replace(IMAGE_MARK, PLACEHOLDER_IMG)



# ---------------------------------------------------------------------- #
# AI builder ("creative thinking")
# ---------------------------------------------------------------------- #
def _doc_to_md(html):
    """Doc HTML -> compact markdown-ish text for the model."""
    soup = BeautifulSoup(html or "", "lxml")
    out = []
    for el in (soup.body or soup).descendants:
        nm = getattr(el, "name", None)
        if nm and re.match(r"h[1-6]$", nm):
            out.append("\n" + "#" * int(nm[1]) + " " + el.get_text(" ", strip=True))
        elif nm == "p":
            t = el.get_text(" ", strip=True)
            if t:
                out.append(t)
        elif nm == "li":
            out.append("- " + el.get_text(" ", strip=True))
        elif nm == "table":
            rows = []
            for tr in el.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                out.append("\n".join(rows))
    seen, dedup = set(), []
    for line in out:
        key = line.strip()
        if key and key in seen:
            continue
        seen.add(key)
        dedup.append(line)
    return "\n".join(dedup).strip()


def _slot_kind(sec):
    if sec.find(class_=re.compile(r"\bfaq-item\b")):
        return "faq"
    if sec.find(class_=re.compile(r"card-app-card|form-card")):
        return "cards"
    if sec.find("table"):
        return "table"
    return "text"


def _design_slots(article):
    slots = []
    for sec in _content_sections(article):
        h = sec.find(["h2", "h3"], class_=re.compile("section-title"))
        if h is None:
            continue
        heading = h.get_text(" ", strip=True)
        slots.append({"id": sec.get("id") or heading, "heading": heading,
                      "kind": _slot_kind(sec), "furniture": _topic(heading) in FURNITURE})
    return slots


_ALLOWED_TAGS = {"p", "h2", "h3", "h4", "h5", "ul", "ol", "li", "table", "thead",
                 "tbody", "tr", "td", "th", "div", "span", "strong", "em", "b",
                 "i", "br", "a", "img"}


def _sanitize(html):
    """Keep only safe tags/attrs from an AI fragment (design classes preserved,
    scripts/styles/handlers removed; FAQ toggle onclick is allowed)."""
    frag = BeautifulSoup(html or "", "lxml")
    for t in frag.find_all(["script", "style", "iframe", "link", "meta",
                            "object", "embed", "form", "input", "button"]):
        t.decompose()
    for el in frag.find_all(True):
        if el.name not in _ALLOWED_TAGS:
            el.unwrap()
            continue
        for a in list(el.attrs):
            al = a.lower()
            val = str(el.attrs[a])
            if al.startswith("on"):
                if not (al == "onclick" and "togglefaq" in val.lower()):
                    del el[a]
            elif al in ("style", "srcset", "onerror", "onload"):
                del el[a]
            elif al == "href" and val.strip().lower().startswith("javascript:"):
                el["href"] = "#"
    body = frag.body or frag
    return body.decode_contents()


def _find_faq_section(article):
    for s in _content_sections(article):
        h = s.find(["h2", "h3"], class_=re.compile("section-title"))
        if h and _topic(h.get_text(" ", strip=True)) == "faq":
            return s
    return None


def _swap_intro_html(root, html):
    descs = root.find_all(class_="pbmit-short-description")
    if not descs or not html.strip():
        return
    keep = None
    for d in descs:
        if "page consists" in d.get_text(" ", strip=True).lower():
            keep = d
            break
    frag = BeautifulSoup(html, "lxml")
    new_nodes = list((frag.body or frag).children)
    anchor = keep or descs[0]
    for nn in new_nodes:
        anchor.insert_before(nn)
    for d in descs:
        if d is not keep:
            d.decompose()


def _apply_plan(root, article, plan):
    intro = plan.get("intro") or []
    if intro:
        html = "".join(
            f'<div class="pbmit-short-description">{_sanitize(p)}</div>'
            for p in intro if str(p).strip())
        _swap_intro_html(root, html)

    secs = _content_sections(article)
    by_id = {s.get("id").lower(): s for s in secs if s.get("id")}

    def find_slot(key):
        k = (key or "").strip().lower()
        if k in by_id:
            return by_id[k]
        for s in secs:
            h = s.find(["h2", "h3"], class_=re.compile("section-title"))
            if not h:
                continue
            ht = h.get_text(" ", strip=True).lower()
            if k and (k in ht or ht in k):
                return s
        return None

    for item in plan.get("sections", []):
        if item.get("action") != "replace" or not item.get("html", "").strip():
            continue
        sec = find_slot(item.get("id", ""))
        if sec is None:
            continue
        h = sec.find(["h2", "h3"], class_=re.compile("section-title"))
        if h is None or _topic(h.get_text(" ", strip=True)) in FURNITURE:
            continue
        body = _sanitize(item["html"])
        if body.strip():
            _replace_section_body(sec, body)

    extra = ""
    for e in plan.get("extra", []):
        body = _sanitize(e.get("html", ""))
        if not body.strip():
            continue
        extra += (f'<section class="content-section">'
                  f'<h2 class="section-title">{_title_html(e.get("title", ""))}</h2>'
                  f'<div class="section-divider"></div>{body}</section>')
    if extra:
        frag = BeautifulSoup(extra, "lxml")
        new_secs = list((frag.body or frag).children)
        anchor = _find_faq_section(article)
        if anchor is None:
            ctas = [s for s in article.find_all("section")
                    if "cta-section" in (s.get("class") or [])]
            anchor = ctas[-1] if ctas else None
        if anchor is not None:
            for ns in new_secs:
                anchor.insert_before(ns)
        else:
            for ns in new_secs:
                article.append(ns)


# ---------------------------------------------------------------------- #
# Images -> placeholder (content images only; keep logo/cert/flags/chrome)
# ---------------------------------------------------------------------- #
_IMG_KEEP = re.compile(r"logo|favicon|cert|flag|sprite|social", re.I)


def _placeholder_images(root):
    for img in root.find_all("img"):
        p, skip = img.parent, False
        while p is not None and getattr(p, "name", None):
            if p.name in ("header", "nav", "footer", "aside"):
                skip = True
                break
            p = p.parent
        if skip:
            continue
        cls = " ".join(img.get("class") or [])
        src = img.get("src", "") or ""
        if _IMG_KEEP.search(cls) or _IMG_KEEP.search(src):
            continue
        img["src"] = PLACEHOLDER_SRC
        classes = img.get("class") or []
        if "api-img-placeholder" not in classes:
            classes.append("api-img-placeholder")
            img["class"] = classes
        for a in ("srcset", "data-src", "data-srcset"):
            if img.has_attr(a):
                del img[a]


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
