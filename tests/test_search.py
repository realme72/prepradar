import httpx
import pytest

from prepradar.sources import search


def fake_request(responses):
    """responses: host -> (status, json). Records the hosts called, in order."""
    calls = []

    def request(method, url, **kw):
        host = httpx.URL(url).host
        calls.append(host)
        status, body = responses[host]
        return httpx.Response(status, json=body, request=httpx.Request(method, url))

    return request, calls


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("TAVILY_API_KEY", "t")
    monkeypatch.setenv("SERPER_API_KEY", "s")
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)


def test_falls_through_to_next_provider_on_quota(keys, monkeypatch):
    request, calls = fake_request({
        "api.tavily.com": (432, {"detail": "plan limit"}),
        "google.serper.dev": (200, {"organic": [{"link": "https://x.com/a", "title": "A", "snippet": "s"}]}),
    })
    monkeypatch.setattr(search.httpx, "request", request)
    provider, results = search.search("q")
    assert provider == "serper"
    assert calls == ["api.tavily.com", "google.serper.dev"]
    assert results[0].url == "https://x.com/a"


def test_providers_without_keys_are_skipped(keys):
    assert [p.name for p in search.provider_chain()] == ["tavily", "serper"]


def test_find_urls_filters_and_dedupes(keys, monkeypatch):
    results = [
        {"url": "https://www.geeksforgeeks.org/zemoso-interview-experience/", "title": "Zemoso Interview", "content": ""},
        {"url": "https://www.geeksforgeeks.org/zemoso-interview-experience/#comments", "title": "Zemoso", "content": ""},
        {"url": "https://www.zemoso.com/careers", "title": "Careers at Zemoso", "content": ""},
        {"url": "https://www.linkedin.com/posts/zemoso-123", "title": "Zemoso", "content": ""},
        {"url": "https://example.com/infosys-interview", "title": "Infosys interview", "content": ""},
    ]
    request, _ = fake_request({"api.tavily.com": (200, {"results": results})})
    monkeypatch.setattr(search.httpx, "request", request)
    urls = [r.url for r in search.find_experience_urls("zemoso")]
    assert urls == ["https://www.geeksforgeeks.org/zemoso-interview-experience/"]
