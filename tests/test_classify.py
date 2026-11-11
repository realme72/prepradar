from prepradar.extract.extractor import classify
from prepradar.models import Page


def page(url):
    return Page(url=url, site="x", title=None, text="Q1. How do you secure an API? Ans. Use OAuth...", published=None)


def test_review_sites_are_candidate_reviews_without_an_llm_call():
    # would raise without an API key / network if it reached the LLM
    for url in ["https://www.glassdoor.co.in/Interview/ZeMoSo-Interview-E825125-RVW75515598.htm",
                "https://www.ambitionbox.com/interviews/zemoso-technologies-interview-questions"]:
        assert classify(page(url), "zemoso").is_firsthand
