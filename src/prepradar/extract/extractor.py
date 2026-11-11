"""Page text -> list[ExtractedQuestion] via OpenAI structured output."""
import re

from openai import OpenAI
from pydantic import BaseModel, Field

from prepradar import config
from prepradar.extract.prompts import CATEGORY_RULES, CLASSIFY, SYSTEM, USER, format_ladders, format_vocabulary
from prepradar.models import GENERIC_TAG, Category, ExtractedQuestion, Function, ExtractionResult, Page, PageCheck

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()  # reads OPENAI_API_KEY from env
    return _client


class TagMatch(BaseModel):
    too_generic: bool = Field(
        description="True if the tag names no concept someone could study, only the kind of question"
    )
    same_as: str | None = Field(description="The existing tag that means the same topic, or null if none does")


def match_tag(proposed: str, candidates: list[str]) -> str | None:
    """Ask the LLM about a proposed tag. Returns the existing tag it duplicates,
    GENERIC_TAG if it's too vague to be a tag, or None if it's a genuinely new topic."""
    resp = client().responses.parse(
        model=config.OPENAI_MODEL,
        instructions=(
            "You maintain a tag vocabulary for interview questions. Tags name a concept a "
            "candidate could study.\n"
            "1. too_generic: true if the tag only says what kind of question it is, or is too "
            "vague to study: 'Algorithm Knowledge', 'Technical Questions', 'Notes', 'Interview "
            "Preparation', 'App Design', 'Low-Level Design'. Concrete topics are fine: "
            "'Greedy', 'Terraform', 'Ownership', 'Conflict Resolution'.\n"
            "2. same_as: the existing tag that names the SAME topic (synonym, abbreviation, or "
            "rewording), else null. A narrower or merely related topic is NOT the same: 'Java "
            "Streams' is not 'Event Streaming', 'GraphQL' is not 'NoSQL', 'Spring Security' is "
            "not 'Spring Boot'."
        ),
        input=f"Proposed tag: {proposed}\nExisting tags: {', '.join(candidates) or '(none)'}",
        text_format=TagMatch,
        temperature=0,
    )
    m = resp.output_parsed
    if m.too_generic:
        return GENERIC_TAG
    return m.same_as if m.same_as in candidates else None


class QuestionMatch(BaseModel):
    same_as: int | None = Field(description="Number of the existing question that is the same question, or null")


def same_question(new: str, existing: list[str]) -> int | None:
    """Ask the LLM whether `new` is a rewording of one of a few similar existing
    questions. Returns that question's index in `existing`, or None."""
    listing = "\n".join(f"{i}. {t}" for i, t in enumerate(existing))
    resp = client().responses.parse(
        model=config.JUDGE_MODEL,
        reasoning=config.JUDGE_REASONING,
        instructions=(
            "Two interview questions are the SAME if they ask for the same thing, so a candidate "
            "who prepared one has prepared the other: a rewording, or the same problem described "
            "in more or less detail ('Write a debounce function' = 'What is debounce? Implement "
            "it'). They are DIFFERENT if the problem or the ask differs, even when the topic is "
            "shared: 'debug a failing API' vs 'debug a slow API', 'kth largest element' vs '2nd "
            "largest element', 'design an auction platform' vs 'track the winning bid', 'rolling "
            "7-day average' vs 'rolling total', 'Leadership Principles' vs 'decision making'. "
            "Wording, level of detail, a request to also explain the concept, or the output "
            "format don't make questions different. A different problem, metric, constraint "
            "or scope does. If unsure, answer null."
        ),
        input=f"New question: {new}\n\nExisting questions:\n{listing}",
        text_format=QuestionMatch,
    )
    i = resp.output_parsed.same_as
    return i if i is not None and 0 <= i < len(existing) else None


CLASSIFY_CHARS = 6000  # the opening of a page is enough to tell a guide from an experience

# Interview-review sections of these sites are candidate reviews by design. They also
# show AI-written model answers, which often fill the opening of the page, and the
# classifier then flip-flopped between candidate_reviews and question_bank. Extraction
# already ignores model answers, so these skip the LLM.
REVIEW_SITE_PATTERNS = (re.compile(r"glassdoor\.[a-z.]+/Interview/", re.I),
                        re.compile(r"ambitionbox\.com/interviews/", re.I))
# Sites whose pages are AI-written summaries of other people's experiences. The
# classifier caught them most of the time, but one passed on a re-run and ended up
# cited on a top question, so they're rejected by rule.
AI_SUMMARY_PATTERNS = (re.compile(r"discuss\.boardinfinity\.com/", re.I),)


def classify(page: Page, company: str) -> PageCheck:
    if any(p.search(page.url) for p in REVIEW_SITE_PATTERNS):
        return PageCheck(evidence=f"{page.site} interview reviews section", page_kind="candidate_reviews")
    if any(p.search(page.url) for p in AI_SUMMARY_PATTERNS):
        return PageCheck(evidence=f"{page.site} posts are AI-written summaries", page_kind="guide")
    resp = client().responses.parse(
        model=config.JUDGE_MODEL,  # gpt-4o-mini believed guides that claim to be 'from candidates'
        reasoning=config.JUDGE_REASONING,
        instructions=CLASSIFY.format(company=company),
        input=USER.format(company=company, site=page.site, title=page.title or "unknown",
                          text=page.text[:CLASSIFY_CHARS]),
        text_format=PageCheck,
    )
    return resp.output_parsed


def extract(page: Page, company: str, vocabulary: dict[str, str]) -> tuple[bool, list[ExtractedQuestion]]:
    """Returns (is_firsthand, questions). vocabulary maps tag name -> category."""
    if not classify(page, company).is_firsthand:
        return False, []
    resp = client().responses.parse(
        model=config.OPENAI_MODEL,
        instructions=SYSTEM.format(company=company, categories=CATEGORY_RULES, ladders=format_ladders(),
                                  vocabulary=format_vocabulary(vocabulary)),
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


class Recategorised(BaseModel):
    id: int
    category: Category


class Recategorisation(BaseModel):
    questions: list[Recategorised]


def recategorise(questions: list[dict]) -> dict[int, str]:
    """Re-sort stored questions (id, category, text) under the current category rules.
    Returns id -> category for the ids the model answered for. Uses the careful
    model: in batches of 60, gpt-4o-mini sometimes misaligned answers with ids
    ("climbing stairs" -> Behavioral)."""
    listing = "\n".join(f"{q['id']} [{q['category']}] {q['text']}" for q in questions)
    resp = client().responses.parse(
        model=config.JUDGE_MODEL,
        reasoning=config.JUDGE_REASONING,
        instructions=(
            "Each line is: id [current category] question. Return every id with its category "
            "under the rules below. Keep the current category unless the rules clearly put the "
            "question elsewhere.\n\n" + CATEGORY_RULES
        ),
        input=listing,
        text_format=Recategorisation,
    )
    ids = {q["id"] for q in questions}
    return {r.id: r.category for r in resp.output_parsed.questions if r.id in ids}


# Shared with the extraction prompt: a level is only ever read off the title.
LEVEL_RULE = (
    "Only pick a rung the title actually states: I/II/III or 1/2/3, intern, new grad, "
    "associate or junior (-> the entry rung), senior, staff, lead, principal, manager, or a "
    "named title like APM or Account Executive. A title without a level ('Software Engineer', "
    "'Backend Engineer', 'Software Development Engineer', 'SRE') is Unknown. A data engineer, "
    "business analyst or BI engineer is the Data function (Business / BI Analyst for analysts "
    "and BI engineers)."
)


class PlacedRole(BaseModel):
    title: str
    function: Function
    position: str


class RolePlacement(BaseModel):
    roles: list[PlacedRole]


def place_roles(titles: list[str]) -> dict[str, tuple[str, str]]:
    """Map role titles as candidates wrote them onto a function and a rung of its
    ladder. Returns title -> (function, position); off-ladder positions become Unknown."""
    from prepradar.roles import FUNCTIONS, UNKNOWN

    resp = client().responses.parse(
        model=config.JUDGE_MODEL,
        reasoning=config.JUDGE_REASONING,
        instructions=(
            "Place each job title on a function and a position on that function's ladder.\n"
            + LEVEL_RULE + "\n"
            + format_ladders()
        ),
        input="\n".join(titles),
        text_format=RolePlacement,
    )
    out = {}
    for r in resp.output_parsed.roles:
        if r.title in titles:
            pos = r.position if r.position in FUNCTIONS[r.function].positions else UNKNOWN
            out[r.title] = (r.function, pos)
    return out
