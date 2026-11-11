"""HTTP API for the React app. Thin layer over store/db, graph and report.

    uv run uvicorn prepradar.api:app --reload --port 8010
"""
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from prepradar.roles import CATEGORIES, FUNCTIONS, TRACKS, UNKNOWN, Scope
from prepradar.store import db
from prepradar.store.embeddings import embed_query, model

REPORTS = Path("reports")


@asynccontextmanager
async def lifespan(_: FastAPI):
    model()  # load the embedding model once at startup, not on the first search
    yield


app = FastAPI(title="PrepRadar", lifespan=lifespan)


def guide_path(scope: Scope) -> Path:
    return REPORTS / f"{scope.slug()}.md"  # same naming as the CLI's save_guide


def scope_of(company: str, function: str, position: str | None, track: str | None, since: int | None) -> Scope:
    try:
        return Scope(company, function, position or None, track or None, since)
    except ValueError as e:  # unknown function, or a position from another ladder
        raise HTTPException(400, str(e))


@app.get("/api/meta")
def meta():
    return {
        "categories": CATEGORIES,
        "functions": {name: f.positions + [UNKNOWN] for name, f in FUNCTIONS.items()},
        "tracks": TRACKS,
    }


@app.get("/api/companies")
def companies():
    with db.connect() as conn:
        return conn.execute(
            """SELECT s.company,
                      count(DISTINCT s.id) FILTER (WHERE s.status = 'extracted') AS sources,
                      (SELECT count(*) FROM questions q WHERE q.company = s.company) AS questions,
                      max(s.fetched_at) AS last_fetched
               FROM sources s GROUP BY s.company ORDER BY s.company"""
        ).fetchall()


@app.get("/api/companies/{company}/scopes")
def scopes(company: str, track: str | None = None, since: int | None = None):
    """Question counts per function and position, for the UI's dropdowns."""
    with db.connect() as conn:
        return db.scope_counts(conn, company, track or None, since)


@app.get("/api/companies/{company}/questions")
def questions(company: str, function: str = "Engineering", position: str | None = None,
              track: str | None = None, since: int | None = None):
    with db.connect() as conn:
        return db.all_questions(conn, scope_of(company, function, position, track, since))


@app.get("/api/companies/{company}/experiences")
def experiences(company: str, function: str = "Engineering", position: str | None = None,
                track: str | None = None, since: int | None = None):
    with db.connect() as conn:
        return db.experiences(conn, scope_of(company, function, position, track, since))


@app.get("/api/companies/{company}/search")
def search(company: str, q: str = Query(min_length=2), k: int = 10, function: str = "Engineering",
           position: str | None = None, track: str | None = None, since: int | None = None):
    with db.connect() as conn:
        rows = db.search(conn, scope_of(company, function, position, track, since), embed_query(q), k)
    for r in rows:
        r["score"] = round(float(r["score"]), 3)
    return rows


@app.get("/api/companies/{company}/guide")
def guide(company: str, function: str = "Engineering", position: str | None = None,
          track: str | None = None, since: int | None = None):
    path = guide_path(scope_of(company, function, position, track, since))
    if not path.exists():
        raise HTTPException(404, "No guide for these filters yet.")
    return {"markdown": path.read_text()}


@app.post("/api/companies/{company}/guide")
def build_guide(company: str, function: str = "Engineering", position: str | None = None,
                track: str | None = None, since: int | None = None):
    """Write a guide from the questions already stored: no searching, one or two LLM calls."""
    from prepradar.report.writer import render_markdown, write_guide

    scope = scope_of(company, function, position, track, since)
    with db.connect() as conn:
        rows = db.all_questions(conn, scope)
    if not any(q["specific"] for q in rows):
        raise HTTPException(404, "Not enough questions for these filters to write a guide.")
    md = render_markdown(scope, write_guide(scope, rows))
    path = guide_path(scope)
    path.parent.mkdir(exist_ok=True)
    path.write_text(md)
    return {"markdown": md}


class RunRequest(BaseModel):
    company: str
    function: str = "Engineering"
    position: str | None = None
    track: str | None = None
    since: int | None = None
    refresh: bool = False


@app.post("/api/runs")
def run(req: RunRequest):
    """Run the LangGraph pipeline and stream each node's decisions as Server-Sent Events."""
    from prepradar.graph.build import build

    scope = scope_of(req.company.strip().lower(), req.function, req.position, req.track, req.since)

    def events():
        inputs = {"scope": scope, "limit": 10, "refresh": req.refresh, "with_guide": True}
        final: dict = {}
        try:
            for update in build().stream(inputs, stream_mode="updates"):
                for node, changes in update.items():
                    final.update(changes)
                    for line in changes.get("log", []):
                        yield f"data: {json.dumps({'node': node, 'message': line})}\n\n"
            if final.get("guide_md"):
                path = guide_path(scope)
                path.parent.mkdir(exist_ok=True)
                path.write_text(final["guide_md"])
            yield f"data: {json.dumps({'done': True, 'gaps': final.get('gaps') or []})}\n\n"
        except Exception as e:  # surface failures (quota, missing key) to the UI
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    # a sync generator: Starlette iterates it in a worker thread, so the graph's
    # blocking calls (HTTP, LLM, Postgres) don't stall the server
    return StreamingResponse(events(), media_type="text/event-stream")
