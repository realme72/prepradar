"""Page text -> list[ExtractedQuestion] via OpenAI structured output."""
from openai import OpenAI

from prepradar import config
from prepradar.extract.prompts import SYSTEM, USER
from prepradar.models import ExtractedQuestion, ExtractionResult, Page

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()  # reads OPENAI_API_KEY from env
    return _client


def extract(page: Page, company: str) -> list[ExtractedQuestion]:
    resp = client().responses.parse(
        model=config.OPENAI_MODEL,
        instructions=SYSTEM.format(company=company),
        input=USER.format(
            company=company,
            site=page.site,
            title=page.title or "unknown",
            text=page.text[: config.MAX_PAGE_CHARS],
        ),
        text_format=ExtractionResult,
        temperature=0,
    )
    result: ExtractionResult = resp.output_parsed
    if not result.is_interview_content:
        return []
    posted_year = int(page.published[:4]) if page.published else None
    return [
        ExtractedQuestion(**q.model_dump(), company=company, source_url=page.url, posted_year=posted_year)
        for q in result.questions
    ]
