"""Graph nodes and routing functions.

A node takes the state and returns the fields it changed. A router takes the
state and returns the name of the next node; LangGraph calls it on a
conditional edge.
"""
from datetime import datetime, timedelta, timezone

from prepradar.graph.state import GraphState
from prepradar.pipeline import Candidate, ingest
from prepradar.sources.search import QUERY_TEMPLATES, find_experience_urls
from prepradar.store import db

MIN_TOTAL = 30            # fewer cached questions than this -> search
MIN_PER_CATEGORY = 3      # a core category below this is a gap
MAX_RETRIES = 2           # gap-filling search rounds per run
FRESH_FOR = timedelta(days=30)

# Categories a candidate on each track should expect to prepare.
CORE_CATEGORIES = {
    "Backend": ["DSA", "LLD", "HLD", "Backend", "Database", "Behavioral"],
    "Frontend": ["DSA", "Frontend", "HLD", "Behavioral"],
    "Fullstack": ["DSA", "LLD", "HLD", "Backend", "Database", "Frontend", "Behavioral"],
    "DevOps": ["DevOps & Cloud", "Backend", "Behavioral"],
    "ML/AI": ["ML/AI", "DSA", "Behavioral"],
}
DEFAULT_CORE = CORE_CATEGORIES["Backend"]

# One targeted search per thin category.
GAP_QUERIES = {
    "DSA": "{company} coding round interview questions",
    "LLD": "{company} low level design OOP interview",
    "HLD": "{company} system design interview round",
    "Backend": "{company} {role} technical interview questions",
    "Database": "{company} SQL DBMS interview questions",
    "Messaging & Streaming": "{company} kafka interview questions",
    "DevOps & Cloud": "{company} devops interview questions",
    "Frontend": "{company} frontend react interview questions",
    "ML/AI": "{company} machine learning interview questions",
    "Behavioral": "{company} HR managerial round interview",
}


def core_for(track: str | None) -> list[str]:
    return CORE_CATEGORIES.get(track, DEFAULT_CORE)


# ── nodes ────────────────────────────────────────────────────────────────────

def check_cache(state: GraphState) -> dict:
    with db.connect() as conn:
        total = sum(db.category_counts(conn, state["company"], state.get("track"), state.get("since")).values())
        last = db.last_fetched(conn, state["company"])
    fresh = last is not None and datetime.now(timezone.utc) - last < FRESH_FOR
    cached = total >= MIN_TOTAL and fresh and not state.get("refresh")
    why = (f"{total} questions cached, last fetched {last:%Y-%m-%d}" if last else "nothing cached")
    return {"cached": cached, "retries": 0, "gaps": None,
            "log": [f"check_cache: {why} → {'use cache' if cached else 'search'}"]}


def plan_queries(state: GraphState) -> dict:
    company, gaps = state["company"], state.get("gaps")
    if gaps is None:  # first round: broad queries
        queries = [t.format(company=company) for t in QUERY_TEMPLATES]
        return {"queries": queries, "log": [f"plan_queries: {len(queries)} broad queries"]}
    role = (state.get("track") or "software engineer").lower()
    done = set(state.get("searched", []))
    queries = [q for q in (GAP_QUERIES[g].format(company=company, role=role) for g in gaps) if q not in done]
    retries = state.get("retries", 0) + 1
    return {"queries": queries, "retries": retries,
            "log": [f"plan_queries: retry {retries}, targeting {', '.join(gaps)}"]}


def search(state: GraphState) -> dict:
    results = find_experience_urls(state["company"], state["queries"]) if state["queries"] else []
    candidates = [Candidate(r.url, r.title, r.raw_content) for r in results]
    return {"candidates": candidates, "searched": state["queries"],
            "log": [f"search: {len(candidates)} candidate pages"]}


def ingest_pages(state: GraphState) -> dict:
    with db.connect() as conn:
        stats = ingest(conn, state["company"], state["candidates"], state.get("limit", 15))
    return {"last_new_questions": stats.new_questions,
            "log": [f"ingest: {stats.pages} new pages, {stats.new_questions} new questions"
                    + (f", new tags: {', '.join(stats.new_tags)}" if stats.new_tags else "")]}


def coverage_check(state: GraphState) -> dict:
    with db.connect() as conn:
        counts = db.category_counts(conn, state["company"], state.get("track"), state.get("since"))
    gaps = [c for c in core_for(state.get("track")) if counts.get(c, 0) < MIN_PER_CATEGORY]
    summary = ", ".join(f"{c} {counts.get(c, 0)}" for c in core_for(state.get("track")))
    return {"coverage": counts, "gaps": gaps,
            "log": [f"coverage_check: {summary}" + (f" → thin: {', '.join(gaps)}" if gaps else " → all covered")]}


def retrieve(state: GraphState) -> dict:
    with db.connect() as conn:
        questions = db.all_questions(conn, state["company"], state.get("track"), state.get("since"))
    return {"questions": questions, "log": [f"retrieve: {len(questions)} questions"]}


def write_guide(state: GraphState) -> dict:
    from prepradar.report.writer import render_markdown, write_guide as write

    if not state.get("with_guide", True) or not state["questions"]:
        return {"log": ["write_guide: skipped"]}
    g = write(state["company"], state.get("track"), state["questions"])
    note = f", {g.dropped_citations} bad citations removed" if g.dropped_citations else ", all citations valid"
    return {"guide_md": render_markdown(state["company"], state.get("track"), g),
            "log": [f"write_guide: {len(g.guide.sections)} sections from {len(g.questions)} questions{note}"]}


# ── routers ──────────────────────────────────────────────────────────────────

def after_cache(state: GraphState) -> str:
    return "coverage_check" if state["cached"] else "plan_queries"


def after_coverage(state: GraphState) -> str:
    retries = state.get("retries", 0)
    if not state["gaps"]:
        return "retrieve"
    if retries >= MAX_RETRIES:
        return "retrieve"  # tried enough; report what we have and flag the gaps
    if retries > 0 and not state.get("last_new_questions"):
        return "retrieve"  # the last targeted search found nothing new; more won't help
    return "plan_queries"
