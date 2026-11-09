"""Web search for interview-experience URLs.

Providers (tavily, serper, brave) share one interface. SEARCH_PROVIDER picks the
first one to try; if it is out of quota, we fall through to the next provider
that has a key configured, so a free tier running out doesn't stop ingestion.
"""
import os
from dataclasses import dataclass

import httpx

TIMEOUT = 30
# HTTP codes these APIs use for "quota exhausted / plan limit" (Tavily uses 432/433)
QUOTA_CODES = {402, 429, 432, 433}


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    raw_content: str | None = None  # full page text, when the provider returns it


class QuotaExceeded(Exception):
    pass


def _post_or_get(method: str, url: str, **kw) -> dict:
    r = httpx.request(method, url, timeout=TIMEOUT, **kw)
    if r.status_code in QUOTA_CODES:
        raise QuotaExceeded(f"{url} -> HTTP {r.status_code}")
    r.raise_for_status()
    return r.json()


class TavilySearch:
    name, env_key = "tavily", "TAVILY_API_KEY"

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        data = _post_or_get(
            "POST",
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {os.environ[self.env_key]}"},
            # raw content saves a fetch, and Tavily can read pages that block us
            json={"query": query, "max_results": max_results, "include_raw_content": True},
        )
        return [
            SearchResult(r["url"], r.get("title", ""), r.get("content", ""), r.get("raw_content"))
            for r in data.get("results", [])
        ]


class SerperSearch:
    name, env_key = "serper", "SERPER_API_KEY"

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        data = _post_or_get(
            "POST",
            "https://google.serper.dev/search",
            headers={"X-API-KEY": os.environ[self.env_key]},
            json={"q": query, "num": max_results},
        )
        return [SearchResult(r["link"], r.get("title", ""), r.get("snippet", "")) for r in data.get("organic", [])]


class BraveSearch:
    name, env_key = "brave", "BRAVE_API_KEY"

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        data = _post_or_get(
            "GET",
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": os.environ[self.env_key], "Accept": "application/json"},
            params={"q": query, "count": max_results},
        )
        return [
            SearchResult(r["url"], r.get("title", ""), r.get("description", ""))
            for r in data.get("web", {}).get("results", [])
        ]


PROVIDERS = {p.name: p for p in (TavilySearch, SerperSearch, BraveSearch)}


def provider_chain() -> list:
    """Preferred provider first, then the others, keeping only those with a key."""
    first = os.getenv("SEARCH_PROVIDER", "tavily")
    names = [first] + [n for n in PROVIDERS if n != first]
    return [PROVIDERS[n]() for n in names if n in PROVIDERS and os.getenv(PROVIDERS[n].env_key)]


def search(query: str, max_results: int = 10) -> tuple[str, list[SearchResult]]:
    """Returns (provider used, results). Falls through providers on quota errors."""
    chain = provider_chain()
    if not chain:
        raise RuntimeError("no search API key set: add TAVILY_API_KEY (or SERPER_/BRAVE_) to .env")
    for p in chain:
        try:
            return p.name, p.search(query, max_results)
        except QuotaExceeded as e:
            print(f"  {p.name} quota exhausted ({e}), trying next provider")
    raise RuntimeError("all configured search providers are out of quota")


# Queries aimed at places candidates write up their interviews.
QUERY_TEMPLATES = [
    "{company} interview experience",
    "{company} interview experience software engineer geeksforgeeks",
    "{company} interview questions reddit",
    "{company} interview experience leetcode discuss",
    "{company} interview experience medium blog",
    "{company} interview questions glassdoor ambitionbox",
]
# Pages that are never candidate write-ups: job listings, the company's own site, social posts.
SKIP_URL_PARTS = ("/jobs", "/job-listings", "/careers", "linkedin.com", "youtube.com", "instagram.com",
                  "facebook.com", "/salaries", "/reviews/")


def find_experience_urls(company: str, per_query: int = 8) -> list[SearchResult]:
    """Run all query templates, keep unique results that plausibly mention the company."""
    seen: dict[str, SearchResult] = {}
    for template in QUERY_TEMPLATES:
        provider, results = search(template.format(company=company), per_query)
        for r in results:
            url = r.url.split("#")[0]
            text = f"{r.title} {r.snippet} {url}".lower()
            if url in seen or any(p in url.lower() for p in SKIP_URL_PARTS):
                continue
            if company.lower() not in text or company.lower() + "." in url.lower():
                continue  # not about the company, or the company's own website
            seen[url] = r
    return list(seen.values())
