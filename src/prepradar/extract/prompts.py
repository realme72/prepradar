"""Extraction prompts."""

# Step 1: a small, separate call that only decides what kind of page this is.
# Bundled into the extraction call, the model kept saying "firsthand" for guides
# so it could get on with extracting.
CLASSIFY = """You decide whether a web page is a candidate's own report of interviewing at {company}.

First write the evidence (who wrote this, and is it about their own interview?), then
pick page_kind:
- own_experience: one specific person narrates their own interview at {company}: their
  rounds, what they were asked, how it went.
- candidate_reviews: separate reviews, each written by a different candidate (e.g. a
  Glassdoor or AmbitionBox review page). NOT one author summarising what candidates report.
- guide: a prep guide or process overview, even if it quotes or retells candidates'
  stories. "Candidates consistently report...", "this guide covers...", "a candidate
  I'll call X...", second person ("you will be asked..."), or promoting a prep product
  or course all mean guide.
- question_bank: a list of questions "asked at {company}" compiled by a site or course
  (e.g. "Top 50 {company} coding interview questions"), often with model answers, even
  if it says candidates reported them.
- news_or_other: anything else.
"""

# Shared by extraction and `prepradar recategorize`, so both sort questions the same way.
CATEGORY_RULES = """Categories (pick the single best):
  DSA        algorithmic/coding problems (arrays, strings, trees, DP...).
  LLD        object/class design, OOP concepts, design patterns, SOLID, "design a parking lot".
  HLD        system design at scale: architecture, scaling, distributed systems, traffic spikes.
  Backend    language and framework internals (Java, Spring, Node), APIs, auth, concurrency,
             caching, microservices, troubleshooting slow/failing/memory-hungry services,
             OS/networking.
  Database   SQL queries, DBMS concepts, normalization, indexing, transactions, schema
             design, SQL vs NoSQL. Database questions go here; analysing business
             data with SQL (metrics, cohorts, streaks) goes to Data.
  Messaging & Streaming
             Kafka, RabbitMQ/SQS, message queues, pub/sub, event streaming.
  DevOps & Cloud
             CI/CD, deployment pipelines, Git, Docker/Kubernetes, cloud services, monitoring.
  Frontend   JavaScript/TypeScript language (closures, hoisting, event loop, type coercion,
             "what will this print"), debounce/throttle, React, CSS/HTML, browser behaviour
             (DOM, storage, CORS, rendering, what happens when you type a URL), web performance.
  Data       data analyst/engineer work: analytics SQL on business data (rolling metrics,
             streaks, cohorts, retention), ETL and data pipelines, Spark/PySpark, data
             warehousing, product metric and case questions.
  ML/AI      machine learning, data science, GenAI/LLMs.
  Behavioral past projects, conflict, pressure, motivation, HR and salary.
  Other      aptitude, puzzles, anything else.
Examples: "Implement OOP concepts: encapsulation, inheritance..." -> LLD.
"Can a functional interface extend another interface?" -> Backend (Java).
"An API is slow / using too much memory, how do you debug it?" -> Backend
(Production Troubleshooting).
"Handle a sudden 10x traffic spike" -> HLD (Scalability).
"What is normalization? Convert a table to 3NF" -> Database (Normalization).
"Find the kth highest salary from an employee table" -> Database (SQL).
"What tools do you use in your deployment pipeline?" -> DevOps & Cloud (CI/CD).
"Explain closures with an example" / "Implement debounce" -> Frontend (JavaScript).
"Find each user's longest streak of active days" -> Data (Analytics SQL).
"Handle nulls and group-by aggregation in PySpark" -> Data (Spark).
"""

# Step 2: extraction, run only on pages step 1 accepted.
SYSTEM = """You extract interview questions from a candidate's own report of interviewing at {company}.

Extraction rules:
- Only extract questions the candidate reports being ASKED at {company}.
- Ignore navigation, ads, site FAQs, salary info, and prep advice.
- Some sites append model answers (often AI-written) under each question. Extract the
  question only; never turn an answer into a question.
- Rewrite each question as one clear, self-contained sentence. If a candidate wrote
  "asked to reverse LL", write "Reverse a singly linked list."
- One coding problem = one question. Split a list of topics into separate questions
  only when each was clearly asked.
- specific: true if a candidate could prepare an answer to it as written. That includes
  short concept questions ("What is dependency injection?", "Discuss Java Streams")
  and concrete behavioral prompts ("Describe a production bug you fixed").
  specific=false ONLY when the report names an area without the actual question:
  "asked Java questions", "solved two medium problems", "low-medium DSA questions".
- Never invent questions.
- Never include people's names (candidates, interviewers, post authors) in question text.

{categories}
Topic tags: give 1-3 per question. Existing tags, grouped by category:
{vocabulary}
Reuse an existing tag whenever one fits, spelled exactly as listed. Only if none fits,
propose a new short Title Case tag (1-3 words) naming a concept someone could study,
not the specific problem: "Rate Limiting", not "How To Rate Limit Login API";
"Consistency" or "Payment Systems", not "Wallet System". Never propose tags that only
say what kind of question it is ("Algorithm Knowledge", "Technical Questions",
"Interview Preparation", "Low-Level Design"); fewer tags is fine.

track = the role family the candidate interviewed for (Backend, Frontend, Fullstack,
ML/AI, ...). Use General only if the role is unknown.

interview_year = the year the interview took place, only if the title or text states or
clearly implies it (e.g. "Off-Campus 2021", "interviewed in May 2024"). Otherwise null.
Do not use the page's publish date for this.
"""

USER = """Company: {company}
Source site: {site}
Page title: {title}

Page text:
\"\"\"
{text}
\"\"\""""


def format_vocabulary(topics: dict[str, str]) -> str:
    by_cat: dict[str, list[str]] = {}
    for name, cat in topics.items():
        by_cat.setdefault(cat, []).append(name)
    return "\n".join(f"  {cat}: {', '.join(sorted(names))}" for cat, names in by_cat.items())
