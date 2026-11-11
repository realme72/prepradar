"""Core schemas.

QuestionDraft / ExtractionResult are what the LLM fills in (no URL: the model
must never invent one). ExtractedQuestion is the record we store, where we
attach the source URL and posted_year ourselves.
"""
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from prepradar.roles import CATEGORIES, FUNCTIONS, TRACKS, UNKNOWN, engineering_level

# Built from the taxonomy in roles.py (Literal accepts a tuple of values).
Category = Literal[tuple(CATEGORIES)]
Function = Literal[tuple(FUNCTIONS)]
Round = Literal["OA", "Technical", "Managerial", "HR", "Unknown"]
# Engineering specialty; General when unknown or not engineering.
Track = Literal[tuple(TRACKS + ["General"])]

# Starting tag vocabulary, tag -> home category. Loaded into the topics table;
# the extractor may propose new tags, which are added there as 'discovered'.
SEED_TOPICS: dict[str, str] = {
    **dict.fromkeys(
        ["Arrays", "Strings", "Linked List", "Stack/Queue", "Trees", "Graphs", "Dynamic Programming",
         "Sorting/Searching", "Hashing", "Math/Puzzles"], "DSA"),
    **dict.fromkeys(["OOP", "Design Patterns", "SOLID"], "LLD"),
    **dict.fromkeys(["Distributed Systems", "Scalability"], "HLD"),
    **dict.fromkeys(
        ["Java", "Spring Boot", "Node.js", "Python", "Concurrency", "Memory/JVM", "REST/API",
         "Auth/Security", "Caching", "Microservices", "Testing", "OS/Networking",
         "Production Troubleshooting"], "Backend"),
    **dict.fromkeys(
        ["SQL", "DBMS Concepts", "Normalization", "Indexing/Transactions", "Database Design", "NoSQL"],
        "Database"),
    **dict.fromkeys(["Kafka", "Message Queues", "Event Streaming"], "Messaging & Streaming"),
    **dict.fromkeys(["CI/CD", "Docker/Kubernetes", "Cloud", "Monitoring/Observability"], "DevOps & Cloud"),
    **dict.fromkeys(["JavaScript", "TypeScript", "React", "CSS/HTML", "Browser/Performance"], "Frontend"),
    **dict.fromkeys(["Analytics SQL", "ETL/Data Pipelines", "Spark", "Data Warehousing", "Product Metrics"], "Data"),
    **dict.fromkeys(["Machine Learning", "GenAI/LLM"], "ML/AI"),
    **dict.fromkeys(["Project Discussion", "HR"], "Behavioral"),
    **dict.fromkeys(["User Empathy", "Feature Prioritisation"], "Product Sense"),
    **dict.fromkeys(["A/B Testing", "North Star Metrics", "Root Cause Analysis"], "Metrics & Experimentation"),
    "Guesstimates": "Estimation",
    **dict.fromkeys(["Objection Handling", "Cold Calling"], "Sales Pitch & Role-play"),
    **dict.fromkeys(["Negotiation", "Pipeline Management"], "Pipeline & Negotiation"),
    **dict.fromkeys(["Hiring", "Performance Management", "Team Building"], "People Management"),
    "Aptitude": "Other",
}


class QuestionDraft(BaseModel):
    text: str = Field(description="The question as asked, rewritten as one clear self-contained question")
    specific: bool = Field(
        description="False only if the report names an area without the actual question"
    )
    category: Category
    topics: list[str] = Field(description="1-3 tags, reusing the given vocabulary whenever one fits")
    round: Round
    role: str | None = Field(description="Role title as written, e.g. 'Senior Software Engineer 1'; null if not stated")
    function: Function
    position: str = Field(description="The rung on the function's ladder (see the prompt), or Unknown")
    track: Track
    interview_year: int | None = Field(
        description="Year the interview happened, ONLY if stated in the text; never use the page publish date"
    )

    @field_validator("role", mode="before")
    @classmethod
    def blank_role_to_none(cls, v):
        # the model sometimes emits the string "null" instead of a JSON null
        return None if isinstance(v, str) and v.strip().lower() in ("", "null", "none", "n/a") else v

    @field_validator("topics")
    @classmethod
    def unique_topics(cls, v):
        return list(dict.fromkeys(t.strip() for t in v if t.strip()))

    @model_validator(mode="after")
    def position_on_ladder(self):
        # engineering levels come from the title by rule (see roles.ENGINEERING_LEVELS)
        if self.function == "Engineering" and self.role:
            self.position = engineering_level(self.role)
        # the model may name a rung from another ladder, or invent one
        if self.position not in FUNCTIONS[self.function].positions:
            self.position = UNKNOWN
        if self.function != "Engineering":
            self.track = "General"
        return self


# What kind of page this is. Asking for the evidence and a kind is more reliable
# than a bare yes/no: the model has to commit to a reading of the page.
PageKind = Literal[
    "own_experience",      # one person narrates their own interview at the company
    "candidate_reviews",   # separate reviews, each by a different candidate (Glassdoor-style)
    "guide",               # prep guide, process overview, "how to crack", even with anecdotes
    "question_bank",       # list of questions "asked at" the company, often with answers
    "news_or_other",
]
FIRSTHAND_KINDS = {"own_experience", "candidate_reviews"}


class PageCheck(BaseModel):
    evidence: str = Field(description="One sentence on who wrote this and whether it is their own interview")
    page_kind: PageKind

    @property
    def is_firsthand(self) -> bool:
        return self.page_kind in FIRSTHAND_KINDS


class ExtractionResult(BaseModel):
    questions: list[QuestionDraft]


class ExtractedQuestion(QuestionDraft):
    company: str
    source_url: HttpUrl
    posted_year: int | None = None  # from page metadata, set by our code


# A tag judge's verdict for a proposed tag that names no studyable concept.
GENERIC_TAG = "<generic>"


class Page(BaseModel):
    url: str
    site: str
    title: str | None = None
    text: str
    published: str | None = None


class Query(BaseModel):
    company: str
    track: Track | None = None
    min_year: int | None = None
