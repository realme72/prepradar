"""Publishing the free live site's data.

    export   database -> web/public/data/*.json (public: anyone can download these)
             and private/<company>.json (subscribers only: the Worker serves it from
             KV to signed-in users with an active subscription).

What's free in every company: the first half of each category's questions (most
reported first), the newest FREE_STORIES candidate stories per function, and the
opening sections of each guide. Locked items stay in the public file only as
outlines (category, topics, outcome...), never their text, so the blurred cards on
the site can't be read with "inspect element".
"""
import base64
import json
import math
import re
from datetime import date
from pathlib import Path

import numpy as np

from prepradar.roles import CATEGORIES, FUNCTIONS, RELATED_TRACKS, TRACKS, UNKNOWN, Scope
from prepradar.store import db

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "web" / "public" / "data"
PRIVATE_DIR = ROOT / "private"
REPORTS = ROOT / "reports"

FREE_SHARE = 0.5          # of each category's specific questions, most reported first
FREE_STORIES = 3          # newest candidate stories per function, shown in full for free
FREE_GUIDE_SECTIONS = 3   # "At a glance", "Process" and the first category section
SINCE_YEARS_BACK = [1, 2, 3, 5]  # the UI's Year options; guides saved for these are exported


def _quantise(vec) -> str:
    """384 floats -> 384 int8 as base64 (512 chars instead of ~2.5k). Ranking by dot
    product barely changes: the vectors are normalised, so x*127 keeps 2-3 digits."""
    vec = np.asarray(vec.to_numpy() if hasattr(vec, "to_numpy") else vec, dtype=np.float32)
    return base64.b64encode(np.clip(np.round(vec * 127), -127, 127).astype(np.int8).tobytes()).decode()


def guide_preview(md: str) -> str:
    """The free part of a guide: the first sections, then a note naming the rest.
    'Cited questions' and 'Sources' stay so [Q#]/[S#] links in the preview still work."""
    parts = re.split(r"(?m)^(?=## )", md)
    head, sections = parts[0], parts[1:]
    heading = lambda s: s.split("\n", 1)[0].removeprefix("## ").strip()
    keep = {"Cited questions", "Sources"}
    rest = sections[FREE_GUIDE_SECTIONS:]
    locked = [s for s in rest if heading(s) not in keep]
    note = (f"## 🔒 {len(locked)} more sections for subscribers\n\n"
            + ", ".join(heading(s) for s in locked) + "\n\n") if locked else ""
    return head + "".join(sections[:FREE_GUIDE_SECTIONS]) + note + "".join(s for s in rest if heading(s) in keep)


def _saved_guides(company: str) -> list[dict]:
    """Full guides already written for this company, under every scope the UI can ask for."""
    this_year = date.today().year
    out = []
    for fn, f in FUNCTIONS.items():
        for pos in [None] + f.positions + [UNKNOWN]:
            for track in [None] + (TRACKS if fn == "Engineering" else []):
                for since in [None] + [this_year - n for n in SINCE_YEARS_BACK]:
                    scope = Scope(company, fn, pos, track, since)
                    path = REPORTS / f"{scope.slug()}.md"
                    if path.exists():
                        out.append({"function": fn, "position": pos or "", "track": track or "",
                                    "since": since, "markdown": path.read_text()})
    return out


def _company_questions(conn, company: str) -> list[dict]:
    rows = conn.execute(f"{db.QUESTION_VIEW}, q.embedding FROM questions q WHERE q.company = %s ORDER BY q.id",
                        (company,)).fetchall()
    for r in rows:
        r["e"] = _quantise(r.pop("embedding"))
    return rows


def _company_stories(conn, company: str) -> list[dict]:
    return conn.execute(
        """SELECT e.id, e.role, e.function, e.position, e.track, e.interview_year, e.posted_year, e.outcome,
                  e.difficulty, e.duration, e.summary, e.rounds, e.tips, s.url, s.site
           FROM experiences e JOIN sources s ON s.id = e.source_id WHERE e.company = %s
           ORDER BY coalesce(e.interview_year, e.posted_year) DESC NULLS LAST, e.id DESC""",
        (company,),
    ).fetchall()


def free_question_ids(questions: list[dict]) -> set[int]:
    """The first half (rounded up) of each function + category's specific questions,
    ranked the way the site lists them. Vague reports are all free: they name no problem."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for q in questions:
        if q["specific"]:
            groups.setdefault((q["function"], q["category"]), []).append(q)
    free = {q["id"] for q in questions if not q["specific"]}
    for qs in groups.values():
        qs.sort(key=lambda q: (-q["times_reported"], -(q["interview_year"] or q["posted_year"] or 0), q["id"]))
        free |= {q["id"] for q in qs[: math.ceil(len(qs) * FREE_SHARE)]}
    return free


def question_outline(q: dict) -> dict:
    """A locked question on the public site: where it belongs and how often it came up,
    but not its text, sources or embedding."""
    return {k: q[k] for k in ("id", "specific", "category", "round", "function", "position", "track",
                              "interview_year", "posted_year", "times_reported", "topics")} | {"locked": True}


def story_outline(story: dict) -> dict:
    """A locked story on the public site: enough to see it exists, none of its content."""
    return {k: story[k] for k in ("id", "function", "position", "track", "interview_year", "posted_year",
                                  "outcome", "difficulty")} | {"rounds_count": len(story["rounds"]), "locked": True}


def export(out_dir: Path = DATA_DIR, private_dir: Path = PRIVATE_DIR) -> dict:
    """Write index.json and, per company, a public <company>.json and a private one.
    Returns {company: question count}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    with db.connect() as conn:
        companies = conn.execute(
            "SELECT company, count(*) AS questions FROM questions GROUP BY company ORDER BY company"
        ).fetchall()
        for c in companies:
            name = c["company"]
            questions = _company_questions(conn, name)
            free_q = free_question_ids(questions)
            stories = _company_stories(conn, name)
            seen: dict[str, int] = {}
            free_s = set()
            for s in stories:  # newest first
                seen[s["function"]] = seen.get(s["function"], 0) + 1
                if seen[s["function"]] <= FREE_STORIES:
                    free_s.add(s["id"])
            guides = _saved_guides(name)

            public = {
                "company": name,
                "questions": [q if q["id"] in free_q else question_outline(q) for q in questions],
                "experiences": [s if s["id"] in free_s else story_outline(s) for s in stories],
                "guides": [g | {"markdown": guide_preview(g["markdown"]), "locked": True} for g in guides],
            }
            private = {
                "company": name,
                "questions": [q for q in questions if q["id"] not in free_q],
                "experiences": [s for s in stories if s["id"] not in free_s],
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
