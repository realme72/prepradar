"""HTTP API for the React app. Thin layer over store/db, graph and report.

    uv run uvicorn prepradar.api:app --reload --port 8010
"""
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from prepradar.models import Category, Track
from prepradar.store import db
from prepradar.store.embeddings import embed_query, model

REPORTS = Path("reports")
CATEGORIES = list(Category.__args__)
TRACKS = [t for t in Track.__args__ if t != "General"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    model()  # load the embedding model once at startup, not on the first search
    yield


app = FastAPI(title="PrepRadar", lifespan=lifespan)


def guide_path(company: str, track: str | None) -> Path:
    # same naming as the CLI's save_guide
    return REPORTS / (company + (f"-{track.lower().replace('/', '-')}" if track else "") + ".md")


@app.get("/api/meta")
def meta():
    return {"categories": CATEGORIES, "tracks": TRACKS}


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


@app.get("/api/companies/{company}/questions")
def questions(company: str, track: str | None = None, since: int | None = None):
    with db.connect() as conn:
        rows = db.all_questions(conn, company, track, since)
    if not rows:
        raise HTTPException(404, f"no questions for {company}")
    return rows


@app.get("/api/companies/{company}/search")
def search(company: str, q: str = Query(min_length=2), k: int = 10,
           track: str | None = None, since: int | None = None):
    with db.connect() as conn:
        rows = db.search(conn, company, embed_query(q), k, track, since)
    for r in rows:
        r["score"] = round(float(r["score"]), 3)
    return rows


@app.get("/api/companies/{company}/guide")
def guide(company: str, track: str | None = None):
    path = guide_path(company, track)
    if not path.exists():
        raise HTTPException(404, "no guide yet; start a run to generate one")
    return {"markdown": path.read_text()}


class RunRequest(BaseModel):
    company: str
    track: str | None = None
    since: int | None = None
    refresh: bool = False


@app.post("/api/runs")
def run(req: RunRequest):
    """Run the LangGraph pipeline and stream each node's decisions as Server-Sent Events."""
    from prepradar.graph.build import build

    company = req.company.strip().lower()

    def events():
        inputs = {"company": company, "track": req.track, "since": req.since,
                  "limit": 10, "refresh": req.refresh, "with_guide": True}
        final: dict = {}
        try:
            for update in build().stream(inputs, stream_mode="updates"):
                for node, changes in update.items():
                    final.update(changes)
                    for line in changes.get("log", []):
                        yield f"data: {json.dumps({'node': node, 'message': line})}\n\n"
            if final.get("guide_md"):
                path = guide_path(company, req.track)
                path.parent.mkdir(exist_ok=True)
                path.write_text(final["guide_md"])
            yield f"data: {json.dumps({'done': True, 'gaps': final.get('gaps') or []})}\n\n"
        except Exception as e:  # surface failures (quota, missing key) to the UI
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    # a sync generator: Starlette iterates it in a worker thread, so the graph's
    # blocking calls (HTTP, LLM, Postgres) don't stall the server
    return StreamingResponse(events(), media_type="text/event-stream")
