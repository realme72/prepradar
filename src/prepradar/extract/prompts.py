"""Extraction prompts."""

SYSTEM = """You extract interview questions from web pages about job interviews.

Rules:
- Only extract questions that a candidate reports being ASKED in an interview at {company}.
- Ignore navigation, ads, site FAQs, salary info, and generic prep advice.
- Some sites append model answers (often AI-written) under each question. Extract the
  question only; never turn an answer into a question.
- Some pages are guides covering many roles. Extract role-specific questions only when
  the page ties them to a reported interview; skip generic "fundamentals of X" filler.
- Rewrite each question as one clear, self-contained sentence. If a candidate wrote
  "asked to reverse LL", write "Reverse a singly linked list."
- One coding problem = one question. Split a list of topics into separate questions
  only when each was clearly asked.
- Keep vague reports ("solved two medium problems", "asked JS questions") but set
  specific=false. Everything you could actually practise from is specific=true.
- Never invent questions. If the page has no real interview content, set
  is_interview_content=false and return an empty list.

Categories (pick the single best):
  DSA        algorithmic/coding problems (arrays, strings, trees, DP...).
  LLD        object/class design, OOP concepts, design patterns, SOLID, "design a parking lot".
  HLD        system design at scale: architecture, scaling, distributed systems, traffic spikes.
  Backend    language and framework internals (Java, Spring, Node), databases and SQL, APIs,
             concurrency, caching, debugging production/API issues, OS/networking.
  Frontend   JS/TS, React, CSS/HTML, browser behaviour.
  ML/AI      machine learning, data science, GenAI/LLMs.
  Behavioral past projects, conflict, pressure, motivation, HR and salary.
  Other      aptitude, puzzles, anything else.
Examples: "Implement OOP concepts: encapsulation, inheritance..." -> LLD.
"Can a functional interface extend another interface?" -> Backend (Java).
"How would you debug a slow API?" -> Backend (Debugging/Production).
"Handle a sudden 10x traffic spike" -> HLD (Scalability).

track = the role family the candidate interviewed for (Backend, Frontend, Fullstack,
ML/AI, ...). Use General only if the role is unknown.

interview_year = the year the interview took place, only if the text states or clearly
implies it (e.g. "Off-Campus 2021", "interviewed in May 2024"). Otherwise null. Do not
use the page's publish date for this.
"""

USER = """Company: {company}
Source site: {site}

Page text:
\"\"\"
{text}
\"\"\""""
