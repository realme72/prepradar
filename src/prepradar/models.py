"""Core schemas.

QuestionDraft / ExtractionResult are what the LLM fills in (no URL: the model
must never invent one). ExtractedQuestion is the stored record, where we attach
the source URL and posted_year ourselves.
"""
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

Category = Literal[
    "DSA", "LLD", "HLD", "Backend", "Database", "Messaging & Streaming",
    "Frontend", "ML/AI", "Behavioral", "Other",
]
Round = Literal["OA", "Technical", "Managerial", "HR", "Unknown"]
# Role family the candidate interviewed for; retrieval filters on this.
Track = Literal["Backend", "Frontend", "Fullstack", "ML/AI", "Data", "Mobile", "QA", "DevOps", "Product", "General"]
# Fixed vocabulary so tags group cleanly; one question can carry several.
Topic = Literal[
    # DSA
    "Arrays", "Strings", "Linked List", "Stack/Queue", "Trees", "Graphs", "Dynamic Programming",
    "Sorting/Searching", "Hashing", "Math/Puzzles",
    # Backend
    "Java", "Spring Boot", "Node.js", "Python", "Concurrency", "Memory/JVM", "REST/API",
    "Auth/Security", "Caching", "Microservices", "Testing", "OS/Networking",
    # Database
    "SQL", "DBMS Concepts", "Normalization", "Indexing/Transactions", "Database Design", "NoSQL",
    # Messaging & Streaming
    "Kafka", "Message Queues", "Event Streaming",
    # Design
    "OOP", "Design Patterns", "SOLID", "Distributed Systems", "Scalability", "Debugging/Production",
    # Frontend
    "JavaScript", "TypeScript", "React", "CSS/HTML", "Browser/Performance",
    # Infra / ML / other
    "DevOps/CI-CD", "Cloud", "Machine Learning", "GenAI/LLM", "Aptitude", "Project Discussion", "HR",
]


class QuestionDraft(BaseModel):
    text: str = Field(description="The question as asked, rewritten as one clear self-contained question")
    specific: bool = Field(
        description="False if too vague to practise from, e.g. 'Solve two medium problems' or 'Asked JS questions'"
    )
    category: Category
    topics: list[Topic] = Field(description="1-3 topic tags")
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
        return list(dict.fromkeys(v))


class ExtractionResult(BaseModel):
    is_interview_content: bool = Field(description="False if the page has no real interview experience/questions")
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
