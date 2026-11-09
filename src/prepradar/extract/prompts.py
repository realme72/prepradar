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
- specific: true if a candidate could prepare an answer to it as written. That includes
  short concept questions ("What is dependency injection?", "Discuss Java Streams")
  and concrete behavioral prompts ("Describe a production bug you fixed").
  specific=false ONLY when the report names an area without the actual question:
  "asked Java questions", "solved two medium problems", "low-medium DSA questions".
- Never invent questions. If the page has no real interview content, set
  is_interview_content=false and return an empty list.

Categories (pick the single best):
  DSA        algorithmic/coding problems (arrays, strings, trees, DP...).
  LLD        object/class design, OOP concepts, design patterns, SOLID, "design a parking lot".
  HLD        system design at scale: architecture, scaling, distributed systems, traffic spikes.
  Backend    language and framework internals (Java, Spring, Node), APIs, auth, concurrency,
             caching, microservices, debugging production/API issues, OS/networking.
  Database   SQL queries, DBMS concepts, normalization, indexing, transactions, schema
             design, SQL vs NoSQL. Any question mainly about a database goes here.
  Messaging & Streaming
             Kafka, RabbitMQ/SQS, message queues, pub/sub, event streaming, event-driven
             pipelines.
  Frontend   JS/TS, React, CSS/HTML, browser behaviour.
  ML/AI      machine learning, data science, GenAI/LLMs.
  Behavioral past projects, conflict, pressure, motivation, HR and salary.
  Other      aptitude, puzzles, anything else.
Examples: "Implement OOP concepts: encapsulation, inheritance..." -> LLD.
"Can a functional interface extend another interface?" -> Backend (Java).
"How would you debug a slow API?" -> Backend (Debugging/Production).
"Handle a sudden 10x traffic spike" -> HLD (Scalability).
"What is normalization? Convert a table to 3NF" -> Database (Normalization).
"Find the kth highest salary from an employee table" -> Database (SQL).
"How does Kafka guarantee ordering within a partition?" -> Messaging & Streaming (Kafka).

track = the role family the candidate interviewed for (Backend, Frontend, Fullstack,
ML/AI, ...). Use General only if the role is unknown.

interview_year = the year the interview took place, only if the text states or clearly
implies it, in the page title or text (e.g. "Off-Campus 2021", "interviewed in May
2024"). Otherwise null. Do not use the page's publish date for this.
"""

USER = """Company: {company}
Source site: {site}
Page title: {title}

Page text:
\"\"\"
{text}
\"\"\""""
