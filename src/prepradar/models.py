"""Core schemas. The LLM extractor must return ExtractedQuestion objects."""
from typing import Literal

from pydantic import BaseModel, HttpUrl

Category = Literal["DSA", "LLD", "HLD", "Backend", "Frontend", "Behavioral", "Other"]
Round = Literal["OA", "Technical", "Managerial", "HR", "Unknown"]


class ExtractedQuestion(BaseModel):
    text: str
    category: Category
    round: Round = "Unknown"
    role: str | None = None
    year: int | None = None
    source_url: HttpUrl


class Query(BaseModel):
    company: str
    role: str | None = None
    min_year: int | None = None
