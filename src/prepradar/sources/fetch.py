"""Fetch a URL and reduce it to the main article text.

Sites that block automation (Naukri Code360 bot check, rate limits) return None;
those will go through a paste-your-experience path later.
"""
from urllib.parse import urlparse

import httpx
import trafilatura

from prepradar.models import Page

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
}
BLOCK_MARKERS = ("Almost there... just a few more seconds",)
MIN_TEXT_CHARS = 300


def site_of(url: str) -> str:
    host = urlparse(url).netloc.removeprefix("www.")
    return host.split(".")[0]


def fetch(url: str) -> Page | None:
    try:
        r = httpx.get(url, headers=UA, follow_redirects=True, timeout=20)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    doc = trafilatura.bare_extraction(r.text, url=url, with_metadata=True)
    if not doc or not doc.text or len(doc.text) < MIN_TEXT_CHARS:
        return None
    if any(m in doc.text for m in BLOCK_MARKERS):
        return None
    return Page(url=url, site=site_of(url), text=doc.text, published=doc.date)
