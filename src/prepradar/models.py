"""Core schemas.

QuestionDraft / ExtractionResult are what the LLM fills in (no URL: the model
must never invent one). ExtractedQuestion is the record we store, where we
attach the source URL and posted_year ourselves.
"""
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

Category = Literal[
    "DSA", "LLD", "HLD", "Backend", "Database", "Messaging & Streaming", "DevOps & Cloud",
    "Frontend", "ML/AI", "Behavioral", "Other",
]
Round = Literal["OA", "Technical", "Managerial", "HR", "Unknown"]
# Role family the candidate interviewed for; retrieval filters on this.
Track = Literal["Backend", "Frontend", "Fullstack", "ML/AI", "Data", "Mobile", "QA", "DevOps", "Product", "General"]

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
    **dict.fromkeys(["Machine Learning", "GenAI/LLM"], "ML/AI"),
    **dict.fromkeys(["Project Discussion", "HR"], "Behavioral"),
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


class ExtractionResult(BaseModel):
    is_firsthand: bool = Field(
        description="True only if the page is a candidate describing their own interview at the company"
    )
    questions: list[QuestionDraft]


class ExtractedQuestion(QuestionDraft):
    company: str
    source_url: HttpUrl
    posted_year: int | None = None  # from page metadata, set by our code


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
