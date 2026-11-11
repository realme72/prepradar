from prepradar.extract.extractor import classify
from prepradar.models import Page


def page(url):
    return Page(url=url, site="x", title=None, text="Q1. How do you secure an API? Ans. Use OAuth...", published=None)


def test_review_sites_are_candidate_reviews_without_an_llm_call():
    # would raise without an API key / network if it reached the LLM
    for url in ["https://www.glassdoor.co.in/Interview/ZeMoSo-Interview-E825125-RVW75515598.htm",
                "https://www.ambitionbox.com/interviews/zemoso-technologies-interview-questions"]:
        assert classify(page(url), "zemoso").is_firsthand


def test_ai_summary_sites_are_rejected_without_an_llm_call():
    url = "https://discuss.boardinfinity.com/t/amazon-product-manager-interview-questions-experience-guide/22860"
    assert not classify(page(url), "amazon").is_firsthand


def test_leetcode_is_never_fetched_only_pasted(monkeypatch):
    from prepradar.sources import fetch

    monkeypatch.setattr(fetch, "fetch", lambda url: (_ for _ in ()).throw(AssertionError("fetched")))
    url = "https://leetcode.com/discuss/post/7464207/amazon-sde-2-interview-experience"
    assert fetch.load_page(url, None, None) is None
    pasted = fetch.load_page(url, None, "Round 1: two DSA problems. " * 20)
    assert pasted is not None and pasted.site == "leetcode"
