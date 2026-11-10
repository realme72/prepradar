from prepradar.sources import fetch

TEXT = "Round 1 was DSA. " * 40


def test_linkedin_uses_provider_text_and_drops_named_title(monkeypatch):
    monkeypatch.setattr(fetch, "fetch", lambda url: (_ for _ in ()).throw(AssertionError("should not fetch")))
    page = fetch.load_page("https://www.linkedin.com/posts/x-activity-1", "Jane Doe on LinkedIn: Zemoso", TEXT)
    assert page.text == TEXT and page.title is None


def test_other_sites_fetch_first(monkeypatch):
    calls = []
    monkeypatch.setattr(fetch, "fetch", lambda url: calls.append(url))
    page = fetch.load_page("https://www.geeksforgeeks.org/zemoso", "Zemoso Interview", TEXT)
    assert calls == ["https://www.geeksforgeeks.org/zemoso"]  # tried first, returned None
    assert page.title == "Zemoso Interview"  # fell back to provider text
