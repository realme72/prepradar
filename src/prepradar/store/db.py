"""Postgres + pgvector access (see db/schema.sql).

pgvector's `<=>` operator is cosine DISTANCE (0 = identical), so similarity
is `1 - (a <=> b)`.
"""
from pathlib import Path

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from prepradar import config
from prepradar.models import SEED_TOPICS, ExtractedQuestion
from prepradar.store.embeddings import embed

SCHEMA = Path(__file__).resolve().parents[3] / "db" / "schema.sql"

# a Backend query should also surface Fullstack interviews, and vice versa
RELATED_TRACKS = {
    "Backend": ["Backend", "Fullstack", "General"],
    "Frontend": ["Frontend", "Fullstack", "General"],
    "Fullstack": ["Backend", "Frontend", "Fullstack", "General"],
}


def connect() -> psycopg.Connection:
    conn = psycopg.connect(config.DATABASE_URL, row_factory=dict_row)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def init(conn: psycopg.Connection) -> int:
    """Create tables and load seed tags. Returns the number of seed tags added."""
    conn.execute(SCHEMA.read_text())
    existing = {r["name"] for r in conn.execute("SELECT name FROM topics")}
    new = [name for name in SEED_TOPICS if name not in existing]
    if new:
        vecs = embed(new)
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO topics (name, category, origin, embedding) VALUES (%s, %s, 'seed', %s)",
                [(name, SEED_TOPICS[name], vec) for name, vec in zip(new, vecs)],
            )
    conn.commit()
    return len(new)


# ── sources ──────────────────────────────────────────────────────────────────

def seen_urls(conn: psycopg.Connection) -> dict[str, str]:
    return {r["url"]: r["status"] for r in conn.execute("SELECT url, status FROM sources")}


def add_source(conn, url: str, company: str, status: str, site=None, title=None, posted_year=None) -> int:
    return conn.execute(
        """INSERT INTO sources (url, company, site, title, posted_year, status)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (url, company, site, title, posted_year, status),
    ).fetchone()["id"]


# ── topics ───────────────────────────────────────────────────────────────────

def vocabulary(conn: psycopg.Connection) -> dict[str, str]:
    return {r["name"]: r["category"] for r in conn.execute("SELECT name, category FROM topics ORDER BY name")}


def resolve_topic(conn, name: str, category: str, judge) -> tuple[int, str, bool]:
    """Map a proposed tag to a topic id. Returns (id, canonical name, created_new).

    judge(proposed, candidate_names) -> matching name or None; called only for
    tags whose nearest neighbours are close but not near-identical.
    """
    row = conn.execute("SELECT id, name FROM topics WHERE lower(name) = lower(%s)", (name,)).fetchone()
    if row:
        return row["id"], row["name"], False

    vec = embed([name])[0]
    near = conn.execute(
        "SELECT id, name, 1 - (embedding <=> %s) AS sim FROM topics ORDER BY embedding <=> %s LIMIT 3",
        (vec, vec),
    ).fetchall()
    if near and near[0]["sim"] >= config.TOPIC_AUTO_MERGE:
        return near[0]["id"], near[0]["name"], False
    # embeddings alone miss obvious matches ("Deployment Pipeline" never ranks
    # "CI/CD" top-3), so the judge also sees every tag in the question's category
    same_cat = conn.execute("SELECT id, name FROM topics WHERE category = %s", (category,)).fetchall()
    close = [r for r in near if r["sim"] >= config.TOPIC_CANDIDATE]
    candidates = list({r["id"]: r for r in [*same_cat, *close]}.values())
    if candidates:
        same = judge(name, [r["name"] for r in candidates])
        for r in candidates:
            if r["name"] == same:
                return r["id"], r["name"], False

    new_id = conn.execute(
        "INSERT INTO topics (name, category, origin, embedding) VALUES (%s, %s, 'discovered', %s) RETURNING id",
        (name, category, vec),
    ).fetchone()["id"]
    return new_id, name, True


# ── questions ────────────────────────────────────────────────────────────────

def add_question(conn, q: ExtractedQuestion, source_id: int, vec: np.ndarray) -> tuple[int, bool]:
    """Insert q, or link it to an existing near-duplicate. Returns (question id, was_duplicate)."""
    row = conn.execute(
        """SELECT id, 1 - (embedding <=> %s) AS sim FROM questions
           WHERE company = %s ORDER BY embedding <=> %s LIMIT 1""",
        (vec, q.company, vec),
    ).fetchone()
    if row and row["sim"] >= config.DEDUPE_THRESHOLD:
        qid, dup = row["id"], True
    else:
        qid, dup = conn.execute(
            """INSERT INTO questions (company, text, specific, category, round, role, track,
                                      interview_year, posted_year, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (q.company, q.text, q.specific, q.category, q.round, q.role, q.track,
             q.interview_year, q.posted_year, vec),
        ).fetchone()["id"], False
    conn.execute(
        "INSERT INTO question_sources (question_id, source_id, original_text) VALUES (%s, %s, %s) "
        "ON CONFLICT DO NOTHING",
        (qid, source_id, q.text),
    )
    return qid, dup


def tag_question(conn, question_id: int, topic_id: int) -> None:
    conn.execute(
        "INSERT INTO question_topics (question_id, topic_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (question_id, topic_id),
    )


# ── retrieval ────────────────────────────────────────────────────────────────

QUESTION_VIEW = """
    SELECT q.id, q.text, q.specific, q.category, q.track, q.role,
           q.interview_year, q.posted_year,
           (SELECT count(*) FROM question_sources s WHERE s.question_id = q.id) AS times_reported,
           (SELECT array_agg(t.name ORDER BY t.name) FROM question_topics qt
              JOIN topics t ON t.id = qt.topic_id WHERE qt.question_id = q.id) AS topics,
           (SELECT array_agg(src.url) FROM question_sources s
              JOIN sources src ON src.id = s.source_id WHERE s.question_id = q.id) AS urls
"""


def _filters(company: str, track: str | None, since: int | None) -> tuple[str, list]:
    where, params = ["q.company = %s"], [company]
    if track:
        where.append("q.track = ANY(%s)")
        params.append(RELATED_TRACKS.get(track, [track, "General"]))
    if since:
        where.append("coalesce(q.interview_year, q.posted_year) >= %s")
        params.append(since)
    return " AND ".join(where), params


def all_questions(conn, company: str, track: str | None = None, since: int | None = None) -> list[dict]:
    where, params = _filters(company, track, since)
    return conn.execute(f"{QUESTION_VIEW} FROM questions q WHERE {where}", params).fetchall()


def search(conn, company: str, query_vec: np.ndarray, k: int,
           track: str | None = None, since: int | None = None) -> list[dict]:
    """Hybrid retrieval: SQL filters narrow the rows, vector distance ranks them.

    Vague questions are excluded: "solve two medium problems" matches the shape
    of almost any query and crowds out real questions.
    """
    where, params = _filters(company, track, since)
    return conn.execute(
        f"""{QUESTION_VIEW}, 1 - (q.embedding <=> %s) AS score
            FROM questions q WHERE {where} AND q.specific
            ORDER BY q.embedding <=> %s LIMIT %s""",
        [query_vec, *params, query_vec, k],
    ).fetchall()
