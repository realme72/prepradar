"""Graph nodes and routing functions.

A node takes the state and returns the fields it changed. A router takes the
state and returns the name of the next node; LangGraph calls it on a
conditional edge.
"""
from datetime import datetime, timedelta, timezone

from prepradar.graph.state import GraphState
from prepradar.pipeline import Candidate, ingest
from prepradar.sources.search import broad_queries, find_experience_urls
from prepradar.store import db

MIN_TOTAL = 30            # fewer cached questions than this -> search
MIN_PER_CATEGORY = 3      # a core category below this is a gap
MAX_RETRIES = 2           # gap-filling search rounds per run
FRESH_FOR = timedelta(days=30)

# Targeted searches per thin category. Phrased as "interview experience", never
# "interview questions": the latter mostly finds prep guides and question banks.
# Engineering: tuned per category. Design rounds mostly appear in experienced-hire
# loops, so HLD/LLD ask for those.
GAP_QUERIES = {
    "DSA": ["{company} coding round interview experience",
            "{company} online assessment interview experience"],
    "LLD": ["{company} interview experience low level design round",
            "{company} machine coding round interview experience",
            "{company} SDE 2 interview experience LLD"],
    "HLD": ["{company} system design round interview experience",
            "{company} SDE 2 interview experience system design",
            "{company} senior software engineer interview experience HLD"],
    "Backend": ["{company} {role} interview experience technical round"],
    "Database": ["{company} interview experience SQL DBMS round"],
    "Messaging & Streaming": ["{company} interview experience kafka"],
    "DevOps & Cloud": ["{company} devops engineer interview experience"],
    "Frontend": ["{company} frontend engineer interview experience"],
    "Data": ["{company} data engineer interview experience",
             "{company} data analyst interview experience SQL round"],
    "ML/AI": ["{company} machine learning engineer interview experience"],
    "Behavioral": ["{company} hiring manager round interview experience"],
}
# Other functions: "{company} {role term} interview experience {round name}".
GAP_HINTS = {
    "Product Sense": "product sense round", "Metrics & Experimentation": "metrics round",
    "Estimation": "guesstimate round", "Strategy": "case study round", "Execution": "execution round",
    "Portfolio & Critique": "portfolio review", "Design Exercise": "design challenge",
    "Sales Pitch & Role-play": "role play round", "Pipeline & Negotiation": "sales round",
    "Market & Product Knowledge": "sales interview", "Marketing Strategy": "marketing case study",
    "Campaigns & Growth": "marketing round", "Operations & Process": "operations case study",
    "HR & Recruiting": "HR round", "People Management": "managerial round",
    "Behavioral": "behavioral round", "Data": "SQL round", "Database": "SQL round",
}


def gap_queries(scope, gap: str) -> list[str]:
    if scope.function == "Engineering" and gap in GAP_QUERIES:
        role = f"{scope.track.lower()} engineer" if scope.track else "software engineer"
        return [t.format(company=scope.company, role=role) for t in GAP_QUERIES[gap]]
    hint = GAP_HINTS.get(gap, gap.lower())
    return [f"{scope.company} {term} interview experience {hint}" for term in scope.search_terms()[:2]]


# ── nodes ────────────────────────────────────────────────────────────────────

def check_cache(state: GraphState) -> dict:
    scope = state["scope"]
    with db.connect() as conn:
        total = sum(db.category_counts(conn, scope).values())
        last = db.last_fetched(conn, scope.company)
    fresh = last is not None and datetime.now(timezone.utc) - last < FRESH_FOR
    cached = total >= MIN_TOTAL and fresh and not state.get("refresh")
    why = (f"{total} questions cached, last fetched {last:%Y-%m-%d}" if last else "nothing cached")
    return {"cached": cached, "retries": 0, "gaps": None,
            "log": [f"check_cache: {why} → {'use cache' if cached else 'search'}"]}


def plan_queries(state: GraphState) -> dict:
    scope, gaps = state["scope"], state.get("gaps")
    done = set(state.get("searched", []))
    if gaps is None:  # first round: broad queries
        queries = [q for q in broad_queries(scope) if q not in done]
        return {"queries": queries, "log": [f"plan_queries: {len(queries)} broad queries for {scope.label()}"]}
    queries = [q for g in gaps for q in gap_queries(scope, g) if q not in done]
    retries = state.get("retries", 0) + 1
    return {"queries": queries, "retries": retries,
            "log": [f"plan_queries: retry {retries}, targeting {', '.join(gaps)}"]}


def search(state: GraphState) -> dict:
    results = find_experience_urls(state["scope"].company, state["queries"]) if state["queries"] else []
    candidates = [Candidate(r.url, r.title, r.raw_content) for r in results]
    return {"candidates": candidates, "searched": state["queries"],
            "log": [f"search: {len(candidates)} candidate pages"]}


def ingest_pages(state: GraphState) -> dict:
    with db.connect() as conn:
        stats = ingest(conn, state["scope"].company, state["candidates"], state.get("limit", 15))
    return {"last_new_questions": stats.new_questions,
            "log": [f"ingest: {stats.pages} new write-ups ({stats.rejected} guides/question banks rejected), "
                    f"{stats.new_questions} new questions, {stats.experiences} experiences"
                    + (f", new tags: {', '.join(stats.new_tags)}" if stats.new_tags else "")]}


def coverage_check(state: GraphState) -> dict:
    scope = state["scope"]
    with db.connect() as conn:
        counts = db.category_counts(conn, scope)
    gaps = [c for c in scope.core() if counts.get(c, 0) < MIN_PER_CATEGORY]
    summary = ", ".join(f"{c} {counts.get(c, 0)}" for c in scope.core())
    return {"coverage": counts, "gaps": gaps,
            "log": [f"coverage_check: {summary}" + (f" → thin: {', '.join(gaps)}" if gaps else " → all covered")]}


def retrieve(state: GraphState) -> dict:
    with db.connect() as conn:
        questions = db.all_questions(conn, state["scope"])
    return {"questions": questions, "log": [f"retrieve: {len(questions)} questions"]}


def write_guide(state: GraphState) -> dict:
    from prepradar.report.writer import render_markdown, write_guide as write

    if not state.get("with_guide", True) or not state["questions"]:
        return {"log": ["write_guide: skipped"]}
    g = write(state["scope"], state["questions"])
    note = f", {g.dropped_citations} bad citations removed" if g.dropped_citations else ", all citations valid"
    return {"guide_md": render_markdown(state["scope"], g),
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
