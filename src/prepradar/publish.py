"""Publishing the live site's data, in two tiers per company:

    open         web/public/data/<company>.json, public: anyone can download it.
                 The OPEN_QUESTIONS most reported questions and OPEN_STORIES newest
                 stories in full; every other item, and every guide, only as an outline.
    subscribers  private/<company>.json -> KV "company:<company>". Everything else,
                 including vague reports and full guides.

Outlines carry category, topics, outcome and the like, never text or sources, so the
blurred cards on the site can't be read with "inspect element". Signing in alone
unlocks nothing: it's needed to subscribe (and for quick searches).
"""
import json
from datetime import date
from pathlib import Path

from prepradar.roles import CATEGORIES, FUNCTIONS, RELATED_TRACKS, TRACKS, UNKNOWN
from prepradar.store import db

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "web" / "public" / "data"
PRIVATE_DIR = ROOT / "private"

OPEN_QUESTIONS = 2        # per company, readable without signing in
OPEN_STORIES = 2          # newest, per company, readable without signing in


def _company_questions(conn, company: str) -> list[dict]:
    return conn.execute(f"{db.QUESTION_VIEW} FROM questions q WHERE q.company = %s ORDER BY q.id",
                        (company,)).fetchall()


def _company_stories(conn, company: str) -> list[dict]:
    return conn.execute(
        """SELECT e.id, e.role, e.function, e.position, e.track, e.interview_year, e.posted_year, e.outcome,
                  e.difficulty, e.duration, e.summary, e.rounds, e.tips, s.url, s.site,
                  to_char(s.posted_on, 'YYYY-MM') AS posted_month
           FROM experiences e JOIN sources s ON s.id = e.source_id WHERE e.company = %s
           ORDER BY coalesce(e.interview_year, e.posted_year) DESC NULLS LAST, e.id DESC""",
        (company,),
    ).fetchall()


def _rank(q: dict):
    return (-q["times_reported"], -(q["interview_year"] or q["posted_year"] or 0), q["id"])


def open_question_ids(questions: list[dict]) -> set[int]:
    """The company's OPEN_QUESTIONS most reported specific questions: the signed-out view."""
    return {q["id"] for q in sorted((q for q in questions if q["specific"]), key=_rank)[:OPEN_QUESTIONS]}


def question_outline(q: dict) -> dict:
    """A locked question on the public site: where it belongs and how often it came up,
    but not its text or sources."""
    return {k: q[k] for k in ("id", "specific", "category", "round", "function", "position", "track",
                              "interview_year", "posted_year", "posted_month", "times_reported", "topics")} | {"locked": True}


def story_outline(story: dict) -> dict:
    """A locked story on the public site: enough to see it exists, none of its content."""
    return {k: story[k] for k in ("id", "function", "position", "track", "interview_year", "posted_year",
                                  "posted_month", "outcome", "difficulty")} | {"rounds_count": len(story["rounds"]), "locked": True}


def guide_outline(g: dict) -> dict:
    """A guide on the public site: that it exists for these filters, not its text."""
    return {k: g[k] for k in ("function", "position", "track", "since")} | {"markdown": "", "locked": True}


def export(out_dir: Path = DATA_DIR, private_dir: Path = PRIVATE_DIR) -> dict:
    """Write index.json and, per company, the open and subscriber files.
    Returns {company: question count}."""
    for d in (out_dir, private_dir):
        d.mkdir(parents=True, exist_ok=True)
    written = {}
    with db.connect() as conn:
        companies = conn.execute(
            "SELECT company, count(*) AS questions FROM questions GROUP BY company ORDER BY company"
        ).fetchall()
        for c in companies:
            name = c["company"]
            questions = _company_questions(conn, name)
            open_q = open_question_ids(questions)
            stories = _company_stories(conn, name)
            open_s = {s["id"] for s in stories[:OPEN_STORIES]}  # newest first
            guides = db.company_guides(conn, name)

            public = {
                "company": name,
                "questions": [q if q["id"] in open_q else question_outline(q) for q in questions],
                "experiences": [s if s["id"] in open_s else story_outline(s) for s in stories],
                "guides": [guide_outline(g) for g in guides],
            }
            private = {
                "company": name,
                "questions": [q for q in questions if q["id"] not in open_q],
                "experiences": [s for s in stories if s["id"] not in open_s],
                "guides": guides,
            }
            (out_dir / f"{name}.json").write_text(json.dumps(public, default=str, separators=(",", ":")))
            (private_dir / f"{name}.json").write_text(json.dumps(private, default=str, separators=(",", ":")))
            written[name] = c["questions"]
    index = {
        "updated": date.today().isoformat(),
        "companies": [{"company": c["company"], "questions": c["questions"]} for c in companies],
        "meta": {"categories": CATEGORIES,
                 "functions": {n: f.positions + [UNKNOWN] for n, f in FUNCTIONS.items()},
                 "tracks": TRACKS,
                 "related_tracks": RELATED_TRACKS},
    }
    (out_dir / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    return written
