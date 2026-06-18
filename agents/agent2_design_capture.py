"""
Agent 2 — Design capture.

Given the HTML of a page, extract the CSS and JS references (and inline
styles/scripts) so cloned pages can reuse the same look & feel.
"""
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from core.utils import ok, fail


def run(html: str, base_url: str = ""):
    if not html or not html.strip():
        return fail("Paste the page HTML so the design can be captured.")

    soup = BeautifulSoup(html, "lxml")

    css_links, inline_css = [], []
    for link in soup.find_all("link", rel=lambda v: v and "stylesheet" in v):
        href = link.get("href")
        if href:
            css_links.append(urljoin(base_url, href) if base_url else href)
    for style in soup.find_all("style"):
        if style.string:
            inline_css.append(style.string)

    js_links, inline_js = [], []
    for script in soup.find_all("script"):
        src = script.get("src")
        if src:
            js_links.append(urljoin(base_url, src) if base_url else src)
        elif script.string:
            inline_js.append(script.string)

    # The <body> markup is the visual template we clone into.
    body = soup.body
    template_html = body.decode_contents() if body else html

    data = {
        "css_links": css_links,
        "inline_css_count": len(inline_css),
        "inline_css": inline_css,
        "js_links": js_links,
        "inline_js_count": len(inline_js),
        "template_html": template_html,
    }
    msg = f"Captured {len(css_links)} CSS file(s), {len(js_links)} JS file(s)."
    return ok(data, msg)
