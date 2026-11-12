"""Postgres + pgvector access (see db/schema.sql).

pgvector's `<=>` operator is cosine DISTANCE (0 = identical), so similarity
is `1 - (a <=> b)`.
"""
import hashlib
from pathlib import Path

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Json

from prepradar import config
from prepradar.models import GENERIC_TAG, SEED_TOPICS, Category, ExperienceDraft, ExtractedQuestion
from prepradar.roles import RELATED_TRACKS, Scope
from prepradar.store.embeddings import embed

SCHEMA = Path(__file__).resolve().parents[3] / "db" / "schema.sql"

# a Backend query should also surface Fullstack interviews, and vice versa
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


def content_hash(text: str) -> str:
    # whitespace/case-insensitive, so the same post served by two URLs matches
    return hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest()


def find_same_post(conn, company: str, text: str, title: str | None) -> str | None:
    """URL of an already-stored source with the same content (or, for rows
    stored before hashing, the same title). None if this post is new."""
    row = conn.execute(
        """SELECT url FROM sources WHERE company = %s
           AND (content_hash = %s OR (%s::text IS NOT NULL AND lower(title) = lower(%s)))
           LIMIT 1""",
        (company, content_hash(text), title, title),
    ).fetchone()
    return row["url"] if row else None


def add_source(conn, url: str, company: str, status: str, site=None, title=None, posted_year=None,
               text: str | None = None) -> int:
    return conn.execute(
        """INSERT INTO sources (url, company, site, title, posted_year, status, content_hash)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (url, company, site, title, posted_year, status, content_hash(text) if text else None),
    ).fetchone()["id"]


def forget_source(conn, url: str) -> int:
    """Drop a source that should never have been accepted: its questions go, unless
    another source also reported them, and the URL stays cached as not_firsthand so
    it isn't fetched again. Returns how many questions were deleted."""
    row = conn.execute("SELECT id FROM sources WHERE url = %s", (url,)).fetchone()
    if not row:
        raise RuntimeError(f"unknown source: {url}")
    conn.execute("DELETE FROM question_sources WHERE source_id = %s", (row["id"],))
    conn.execute("DELETE FROM experiences WHERE source_id = %s", (row["id"],))
    deleted = conn.execute(
        """DELETE FROM questions q
           WHERE NOT EXISTS (SELECT 1 FROM question_sources qs WHERE qs.question_id = q.id)"""
    ).rowcount
    conn.execute("UPDATE sources SET status = 'not_firsthand' WHERE id = %s", (row["id"],))
    conn.commit()
    return deleted


# ── topics ───────────────────────────────────────────────────────────────────

def vocabulary(conn: psycopg.Connection) -> dict[str, str]:
    return {r["name"]: r["category"] for r in conn.execute("SELECT name, category FROM topics ORDER BY name")}


# Tags that only restate a category ("System Design" on an HLD question) add nothing.
REDUNDANT_TAGS = {c.lower() for c in Category.__args__} | {
    "system design", "coding", "algorithms", "data structures", "programming", "dsa", "devops", "cloud computing",
    "problem solving", "technical questions", "technical architecture", "technical skills",
}


def resolve_topic(conn, name: str, category: str, judge) -> tuple[int, str, bool] | None:
    """Map a proposed tag to a topic id. Returns (id, canonical name, created_new),
    or None for a tag that merely restates a category or that the judge calls generic.

    judge(proposed, candidate_names) -> matching name, GENERIC_TAG, or None; called
    for every tag that isn't an exact or near-identical match.
    """
    if name.lower() in REDUNDANT_TAGS:
        return None
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
    # always ask before creating a tag: the judge also rejects generic ones
    same = judge(name, [r["name"] for r in candidates])
    if same == GENERIC_TAG:
        return None
    for r in candidates:
        if r["name"] == same:
            return r["id"], r["name"], False

    new_id = conn.execute(
        "INSERT INTO topics (name, category, origin, embedding) VALUES (%s, %s, 'discovered', %s) RETURNING id",
        (name, category, vec),
    ).fetchone()["id"]
    return new_id, name, True


# ── questions ────────────────────────────────────────────────────────────────

def pick_duplicate(near: list[dict], text: str, specific: bool, judge) -> int | None:
    """Which existing question (rows of id, text, specific, sim; most similar first) is
    `text` a duplicate of? Near-identical: the top match. Merely close: ask
    judge(text, texts), but never pair a vague report ("solve a graph problem") with a
    specific question: that would count one report as two for the specific one."""
    if not near:
        return None
    if near[0]["sim"] >= config.DEDUPE_THRESHOLD:
        return near[0]["id"]
    close = [r for r in near if r["sim"] >= config.DEDUPE_JUDGE and r["specific"] == specific]
    if not close or judge is None:
        return None
    i = judge(text, [r["text"] for r in close])
    return close[i]["id"] if i is not None else None


def add_question(conn, q: ExtractedQuestion, source_id: int, vec: np.ndarray, judge=None) -> tuple[int, bool]:
    """Insert q, or link it to an existing duplicate. Returns (question id, was_duplicate).
    judge(new_text, candidate_texts) -> index or None decides the borderline cases."""
    near = conn.execute(
        """SELECT id, text, specific, 1 - (embedding <=> %s) AS sim FROM questions
           WHERE company = %s ORDER BY embedding <=> %s LIMIT 3""",
        (vec, q.company, vec),
    ).fetchall()
    qid = pick_duplicate(near, q.text, q.specific, judge)
    dup = qid is not None
    if not dup:
        qid = conn.execute(
            """INSERT INTO questions (company, text, specific, category, round, role, function, position,
                                      track, interview_year, posted_year, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (q.company, q.text, q.specific, q.category, q.round, q.role, q.function, q.position,
             q.track, q.interview_year, q.posted_year, vec),
        ).fetchone()["id"]
    conn.execute(
        "INSERT INTO question_sources (question_id, source_id, original_text) VALUES (%s, %s, %s) "
        "ON CONFLICT DO NOTHING",
        (qid, source_id, q.text),
    )
    return qid, dup


def merge_questions(conn, keep: int, drop: int) -> None:
    """Fold question `drop` into `keep`: its sources and tags move over, then it's deleted."""
    conn.execute(
        """INSERT INTO question_sources (question_id, source_id, original_text)
           SELECT %s, source_id, original_text FROM question_sources WHERE question_id = %s
           ON CONFLICT DO NOTHING""",
        (keep, drop),
    )
    conn.execute(
        """INSERT INTO question_topics (question_id, topic_id)
           SELECT %s, topic_id FROM question_topics WHERE question_id = %s ON CONFLICT DO NOTHING""",
        (keep, drop),
    )
    conn.execute("DELETE FROM questions WHERE id = %s", (drop,))


def near_duplicate_pairs(conn, company: str | None = None) -> list[dict]:
    """Pairs in the judge band (vague with vague, specific with specific), closest first. Pairs above DEDUPE_THRESHOLD can't
    exist: insert-time dedupe already merged them."""
    return conn.execute(
        """SELECT a.id AS a, a.text AS a_text, b.id AS b, b.text AS b_text,
                  1 - (a.embedding <=> b.embedding) AS sim
           FROM questions a JOIN questions b
             ON a.company = b.company AND a.id < b.id AND a.specific = b.specific
           WHERE (%s::text IS NULL OR a.company = %s)
             AND 1 - (a.embedding <=> b.embedding) >= %s
           ORDER BY sim DESC""",
        (company, company, config.DEDUPE_JUDGE),
    ).fetchall()


def merge_topic(conn, old: str, into: str) -> int:
    """Move every question tagged `old` onto `into`, then delete `old`. Returns questions moved."""
    src = conn.execute("SELECT id FROM topics WHERE lower(name) = lower(%s)", (old,)).fetchone()
    dst = conn.execute("SELECT id FROM topics WHERE lower(name) = lower(%s)", (into,)).fetchone()
    if not src or not dst:
        raise RuntimeError(f"unknown tag: {old if not src else into}")
    moved = conn.execute(
        """INSERT INTO question_topics (question_id, topic_id)
           SELECT question_id, %s FROM question_topics WHERE topic_id = %s
           ON CONFLICT DO NOTHING""",
        (dst["id"], src["id"]),
    ).rowcount
    conn.execute("DELETE FROM topics WHERE id = %s", (src["id"],))  # cascades its question_topics rows
    conn.commit()
    return moved


def sync_tag_categories(conn) -> int:
    """A discovered tag takes the category of the first question that used it. After
    questions are recategorised, move each discovered tag to the category most of its
    questions are in. Returns how many tags moved."""
    moved = conn.execute(
        """UPDATE topics t SET category = m.category
           FROM (SELECT DISTINCT ON (qt.topic_id) qt.topic_id, q.category
                 FROM question_topics qt JOIN questions q ON q.id = qt.question_id
                 GROUP BY qt.topic_id, q.category
                 ORDER BY qt.topic_id, count(*) DESC, q.category) m
           WHERE t.id = m.topic_id AND t.origin = 'discovered' AND t.category <> m.category"""
    ).rowcount
    conn.commit()
    return moved


def delete_topic(conn, name: str) -> None:
    if not conn.execute("DELETE FROM topics WHERE lower(name) = lower(%s)", (name,)).rowcount:
        raise RuntimeError(f"unknown tag: {name}")
    conn.commit()


def tag_question(conn, question_id: int, topic_id: int) -> None:
    conn.execute(
        "INSERT INTO question_topics (question_id, topic_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (question_id, topic_id),
    )


# ── retrieval ────────────────────────────────────────────────────────────────

# A discovered tag stays provisional (stored, offered to the extractor and the judge,
# but not shown) until write-ups from at least this many sources use it. One-off
# tags are usually a single page's wording; a tag two candidates needed is real.
MIN_TAG_SOURCES = 2

TAG_SOURCES = """
    (SELECT count(DISTINCT s.source_id) FROM question_topics qt
       JOIN question_sources s ON s.question_id = qt.question_id WHERE qt.topic_id = t.id)
"""

QUESTION_VIEW = f"""
    SELECT q.id, q.text, q.specific, q.category, q.round, q.function, q.position, q.track, q.role,
           q.interview_year, q.posted_year,
           (SELECT count(*) FROM question_sources s WHERE s.question_id = q.id) AS times_reported,
           (SELECT array_agg(t.name ORDER BY t.name) FROM question_topics qt
              JOIN topics t ON t.id = qt.topic_id
              WHERE qt.question_id = q.id
                AND (t.origin = 'seed' OR {TAG_SOURCES} >= {MIN_TAG_SOURCES})) AS topics,
           (SELECT array_agg(src.url) FROM question_sources s
              JOIN sources src ON src.id = s.source_id WHERE s.question_id = q.id) AS urls
"""


def _filters(scope: Scope) -> tuple[str, list]:
    where, params = ["q.company = %s", "q.function = %s"], [scope.company, scope.function]
    if scope.position:
        where.append("q.position = %s")
        params.append(scope.position)
    if scope.track:
        where.append("q.track = ANY(%s)")
        params.append(RELATED_TRACKS.get(scope.track, [scope.track, "General"]))
    if scope.since:
        where.append("coalesce(q.interview_year, q.posted_year) >= %s")
        params.append(scope.since)
    return " AND ".join(where), params


def category_counts(conn, scope: Scope) -> dict[str, int]:
    """Specific (non-vague) questions per category, under the same filters as retrieval."""
    where, params = _filters(scope)
    rows = conn.execute(
        f"SELECT q.category, count(*) AS n FROM questions q WHERE {where} AND q.specific GROUP BY 1", params
    ).fetchall()
    return {r["category"]: r["n"] for r in rows}


def scope_counts(conn, company: str, track: str | None = None, since: int | None = None) -> list[dict]:
    """Specific questions per (function, position) for one company: the numbers in the
    UI's dropdowns. Track and year filters apply, so a count matches the list it opens."""
    where, params = ["company = %s", "specific"], [company]
    if track:  # only narrows engineering rows; other functions have no track
        where.append("(function <> 'Engineering' OR track = ANY(%s))")
        params.append(RELATED_TRACKS.get(track, [track, "General"]))
    if since:
        where.append("coalesce(interview_year, posted_year) >= %s")
        params.append(since)
    return conn.execute(
        f"""SELECT function, position, count(*) AS questions FROM questions
            WHERE {" AND ".join(where)} GROUP BY 1, 2 ORDER BY 1, 2""",
        params,
    ).fetchall()


# ── experiences ──────────────────────────────────────────────────────────────

def add_experiences(conn, source_id: int, company: str, posted_year: int | None,
                    exps: list[ExperienceDraft]) -> None:
    """Replace the stored stories for a source (re-extracting a page must not double them)."""
    conn.execute("DELETE FROM experiences WHERE source_id = %s", (source_id,))
    for e in exps:
        conn.execute(
            """INSERT INTO experiences (source_id, company, function, position, track, role, interview_year,
                                        posted_year, outcome, difficulty, duration, summary, rounds, tips)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (source_id, company, e.function, e.position, e.track, e.role, e.interview_year, posted_year,
             e.outcome, e.difficulty, e.duration, e.summary, Json([r.model_dump() for r in e.rounds]),
             [t.advice for t in e.tips]),
        )


def experiences(conn, scope: Scope) -> list[dict]:
    """Stories under the same filters as questions (the columns share names), newest first."""
    where, params = _filters(scope)
    return conn.execute(
        f"""SELECT q.id, q.role, q.function, q.position, q.track, q.interview_year, q.posted_year, q.outcome,
                   q.difficulty, q.duration, q.summary, q.rounds, q.tips, s.url, s.site
            FROM experiences q JOIN sources s ON s.id = q.source_id
            WHERE {where}
            ORDER BY coalesce(q.interview_year, q.posted_year) DESC NULLS LAST, q.id DESC""",
        params,
    ).fetchall()


def last_fetched(conn, company: str):
    return conn.execute("SELECT max(fetched_at) AS t FROM sources WHERE company = %s", (company,)).fetchone()["t"]


def all_questions(conn, scope: Scope) -> list[dict]:
    where, params = _filters(scope)
    return conn.execute(f"{QUESTION_VIEW} FROM questions q WHERE {where}", params).fetchall()


def search(conn, scope: Scope, query_vec: np.ndarray, k: int) -> list[dict]:
    """Hybrid retrieval: SQL filters narrow the rows, vector distance ranks them.

    Vague questions are excluded: "solve two medium problems" matches the shape
    of almost any query and crowds out real questions.
    """
    where, params = _filters(scope)
    return conn.execute(
        f"""{QUESTION_VIEW}, 1 - (q.embedding <=> %s) AS score
            FROM questions q WHERE {where} AND q.specific
            ORDER BY q.embedding <=> %s LIMIT %s""",
        [query_vec, *params, query_vec, k],
    ).fetchall()


# ── guides ───────────────────────────────────────────────────────────────────

def save_guide(conn, scope: Scope, md: str) -> None:
    conn.execute(
        """INSERT INTO guides (slug, company, function, position, track, since, markdown)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (slug) DO UPDATE SET markdown = EXCLUDED.markdown, updated_at = now()""",
        (scope.slug(), scope.company, scope.function, scope.position or "", scope.track or "", scope.since, md),
    )
    conn.commit()


def guide(conn, scope: Scope) -> str | None:
    row = conn.execute("SELECT markdown FROM guides WHERE slug = %s", (scope.slug(),)).fetchone()
    return row["markdown"] if row else None


def company_guides(conn, company: str) -> list[dict]:
    return conn.execute(
        "SELECT function, position, track, since, markdown FROM guides WHERE company = %s ORDER BY slug",
        (company,),
    ).fetchall()
