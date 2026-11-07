"""Core schemas.

QuestionDraft / ExtractionResult are what the LLM fills in (no URL: the model
must never invent one). ExtractedQuestion is the stored record, where we attach
the source URL ourselves.
"""
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

Category = Literal["DSA", "LLD", "HLD", "Backend", "Frontend", "Behavioral", "Other"]
Round = Literal["OA", "Technical", "Managerial", "HR", "Unknown"]


class QuestionDraft(BaseModel):
    text: str = Field(description="The question as asked, rewritten as one clear self-contained question")
    category: Category
    round: Round
    role: str | None = Field(description="Role the candidate interviewed for, e.g. 'backend', 'SDE-1'; null if not stated")
    year: int | None = Field(description="Year the interview happened; null if unknown")

    @field_validator("role", mode="before")
    @classmethod
    def blank_role_to_none(cls, v):
        # the model sometimes emits the string "null" instead of a JSON null
        return None if isinstance(v, str) and v.strip().lower() in ("", "null", "none", "n/a") else v


class ExtractionResult(BaseModel):
    is_interview_content: bool = Field(description="False if the page has no real interview experience/questions")
    questions: list[QuestionDraft]


class ExtractedQuestion(QuestionDraft):
    company: str
    source_url: HttpUrl


class Page(BaseModel):
    url: str
    site: str
    text: str
    published: str | None = None


class Query(BaseModel):
    company: str
    role: str | None = None
    min_year: int | None = None
