"""Page text -> list[ExtractedQuestion] via OpenAI structured output."""
from openai import OpenAI
from pydantic import BaseModel, Field

from prepradar import config
from prepradar.extract.prompts import CLASSIFY, SYSTEM, USER, format_vocabulary
from prepradar.models import ExtractedQuestion, ExtractionResult, Page, PageCheck

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()  # reads OPENAI_API_KEY from env
    return _client


class TagMatch(BaseModel):
    same_as: str | None = Field(description="The existing tag that means the same topic, or null if none does")


def match_tag(proposed: str, candidates: list[str]) -> str | None:
    """Ask the LLM whether a proposed tag duplicates one of a few shortlisted tags."""
    resp = client().responses.parse(
        model=config.OPENAI_MODEL,
        instructions=(
            "You maintain a tag vocabulary for interview questions. Decide whether the proposed "
            "tag names the SAME topic as one of the existing tags (synonym, abbreviation, or "
            "rewording). A narrower or merely related topic is NOT the same: 'Java Streams' is "
            "not 'Event Streaming', 'GraphQL' is not 'NoSQL', 'Spring Security' is not 'Spring Boot'."
        ),
        input=f"Proposed tag: {proposed}\nExisting tags: {', '.join(candidates)}",
        text_format=TagMatch,
        temperature=0,
    )
    same = resp.output_parsed.same_as
    return same if same in candidates else None


CLASSIFY_CHARS = 6000  # the opening of a page is enough to tell a guide from an experience


def classify(page: Page, company: str) -> PageCheck:
    resp = client().responses.parse(
        model=config.OPENAI_MODEL,
        instructions=CLASSIFY.format(company=company),
        input=USER.format(company=company, site=page.site, title=page.title or "unknown",
                          text=page.text[:CLASSIFY_CHARS]),
        text_format=PageCheck,
        temperature=0,
    )
    return resp.output_parsed


def extract(page: Page, company: str, vocabulary: dict[str, str]) -> tuple[bool, list[ExtractedQuestion]]:
    """Returns (is_firsthand, questions). vocabulary maps tag name -> category."""
    if not classify(page, company).is_firsthand:
        return False, []
    resp = client().responses.parse(
        model=config.OPENAI_MODEL,
        instructions=SYSTEM.format(company=company, vocabulary=format_vocabulary(vocabulary)),
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
    posted_year = int(page.published[:4]) if page.published else None
    return True, [
        ExtractedQuestion(**q.model_dump(), company=company, source_url=page.url, posted_year=posted_year)
        for q in result.questions
    ]
