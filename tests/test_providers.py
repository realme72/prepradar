"""Falling back from one AI provider to the next (no network: the call itself is stubbed)."""
import httpx
import pytest
from openai import InternalServerError, RateLimitError

from prepradar import config
from prepradar.extract import extractor

A = config.Provider("a", "A_KEY", None, "a-main", "a-judge")
B = config.Provider("b", "B_KEY", None, "b-main", "b-judge", max_chars=100)


def _error(cls, status: int, message: str):
    response = httpx.Response(status, request=httpx.Request("POST", "https://llm.test"))
    return cls(message, response=response, body={"message": message})


class Log(list):
    failures: dict


@pytest.fixture
def calls(monkeypatch):
    log = Log()
    failures = {}  # provider name -> exception to raise

    def fake_call(p, purpose, model, instructions, input, text_format, reasoning, temperature):
        log.append((p.name, model, len(input)))
        if p.name in failures:
            raise failures[p.name]
        return "ok"

    monkeypatch.setattr(config, "PROVIDERS", [A, B])
    monkeypatch.setattr(extractor, "_call", fake_call)
    monkeypatch.setattr(extractor, "_spent", set())
    log.failures = failures
    return log


def ask(purpose="extract", model=None, input="x" * 50):
    return extractor.parse(purpose, model=model or config.OPENAI_MODEL, instructions="", input=input, text_format=None)


def test_a_used_up_daily_quota_moves_the_rest_of_the_run_on(calls):
    calls.failures["a"] = _error(RateLimitError, 429, "Quota exceeded: GenerateRequestsPerDayPerProjectPerModel")
    assert ask() == "ok"
    assert ask() == "ok"
    assert [name for name, *_ in calls] == ["a", "b", "b"]  # a isn't asked again


def test_an_overload_moves_only_that_call(calls):
    calls.failures["a"] = _error(InternalServerError, 503, "The model is overloaded")
    ask()
    del calls.failures["a"]
    ask()
    assert [name for name, *_ in calls] == ["a", "b", "a"]


def test_each_provider_uses_its_own_model_for_the_role(calls, monkeypatch):
    monkeypatch.setattr(config, "JUDGE_MODEL", "judge-role")
    calls.failures["a"] = _error(InternalServerError, 503, "overloaded")
    ask(model="judge-role", purpose="classify")
    assert [m for _, m, _ in calls] == ["a-judge", "b-judge"]


def test_too_big_requests_are_cut_for_pages_and_skipped_for_guides(calls):
    calls.failures["a"] = _error(InternalServerError, 503, "overloaded")
    ask(purpose="extract", input="x" * 5_000)
    assert calls[-1] == ("b", "b-main", 2_000)  # cut, but never below 2,000 chars
    with pytest.raises(extractor.NoProviderLeft):
        ask(purpose="guide", input="x" * 5_000)
