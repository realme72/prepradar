"""Extraction prompts."""

SYSTEM = """You extract interview questions from web pages about job interviews.

Rules:
- Only extract questions that a candidate reports being ASKED in an interview at {company}.
- Ignore navigation, ads, FAQs about the site, salary info, and generic prep advice.
- Some sites append model answers (often AI-written) under each question. Extract the
  question only; never turn an answer into a question.
- Rewrite each question as one clear, self-contained sentence. If a candidate wrote
  "asked to reverse LL", write "Reverse a singly linked list."
- One coding problem = one question. Split lists of topics into separate questions
  only when each was clearly asked ("questions on Java streams and Spring Boot
  annotations" -> two questions).
- Categories:
  DSA = algorithmic/coding problems; LLD = class/object design, design patterns, SOLID;
  HLD = system design at scale; Backend = languages, frameworks, DBs, APIs, concurrency,
  OS/networking; Frontend = JS/TS, React, CSS, browser; Behavioral = experience, HR,
  situational; Other = aptitude, puzzles, anything else.
- Never invent questions. If the page has no real interview content, set
  is_interview_content=false and return an empty list.
"""

USER = """Company: {company}
Page published: {published}
Source site: {site}

Page text:
\"\"\"
{text}
\"\"\""""
