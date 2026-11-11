"""Publishing: the free static site's data, and what a pack unlocks.

    export   database -> web/public/data/*.json (public: the read-only site's whole
             backend) and packs/private/<pack id>.json (paid: served only by the
             Worker, to visitors holding an access token from a verified payment).
    pack     adds a company + function to packs/catalog.json with its price, and
             writes it a fresh guide. The Worker charges from that file.

Everything under web/public/data is downloadable by anyone, so locked content is left
out of it entirely rather than hidden in the UI. A function without a pack in the
catalog has nothing to sell, so all of its content stays free.
"""
import base64
import json
import re
from datetime import date
from pathlib import Path

import numpy as np

from prepradar.roles import CATEGORIES, FUNCTIONS, RELATED_TRACKS, TRACKS, UNKNOWN, Scope
from prepradar.store import db

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "web" / "public" / "data"
PACKS_DIR = ROOT / "packs"
PRIVATE_DIR = PACKS_DIR / "private"
CATALOG = PACKS_DIR / "catalog.json"
REPORTS = ROOT / "reports"

FREE_STORIES = 3          # newest candidate stories per locked function, shown in full for free
FREE_GUIDE_SECTIONS = 3   # "At a glance", "Process" and the first category section
SINCE_YEARS_BACK = [1, 2, 3, 5]  # the UI's Year options; guides saved for these are exported


def pack_id(company: str, function: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", f"{company} {function}".lower()).strip("-")


def catalog() -> dict:
    return json.loads(CATALOG.read_text()) if CATALOG.exists() else {}


def add_pack(company: str, function: str, price_paise: int) -> str:
    """Put a company + function on sale, with a fresh guide (one or two LLM calls):
    a saved guide can predate newer questions, and buyers see the guide first."""
    from prepradar.report.writer import render_markdown, write_guide

    scope = Scope(company, function)
    with db.connect() as conn:
        questions = db.all_questions(conn, scope)
    if not any(q["specific"] for q in questions):
        raise RuntimeError(f"no {function} questions stored for {company}")
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"{scope.slug()}.md").write_text(render_markdown(scope, write_guide(scope, questions)))

    pid = pack_id(company, function)
    entries = catalog()
    entries[pid] = {"company": company, "function": function,
                    "title": f"{company.title()} {function}", "price_paise": price_paise}
    PACKS_DIR.mkdir(exist_ok=True)
    CATALOG.write_text(json.dumps(entries, indent=2) + "\n")
    return pid


# ── export ──────────────────────────────────────────────────────────────────

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
    note = (f"## 🔒 {len(locked)} more sections with the pack\n\n"
            + ", ".join(heading(s) for s in locked) + "\n\n") if locked else ""
    return head + "".join(sections[:FREE_GUIDE_SECTIONS]) + note + "".join(s for s in rest if heading(s) in keep)


def _saved_guides(company: str, function: str) -> list[dict]:
    """Full guides already written for this company and function, under every scope
    the UI can ask for."""
    this_year = date.today().year
    f = FUNCTIONS[function]
    out = []
    for pos in [None] + f.positions + [UNKNOWN]:
        for track in [None] + (TRACKS if function == "Engineering" else []):
            for since in [None] + [this_year - n for n in SINCE_YEARS_BACK]:
                scope = Scope(company, function, pos, track, since)
                path = REPORTS / f"{scope.slug()}.md"
                if path.exists():
                    out.append({"function": function, "position": pos or "", "track": track or "",
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


def _teaser(story: dict, pack: str) -> dict:
    """What a locked story shows on the site: enough to see it exists, none of its content."""
    return {k: story[k] for k in ("id", "function", "position", "track", "interview_year", "posted_year",
                                  "outcome", "difficulty")} | {"rounds_count": len(story["rounds"]), "locked": pack}


def export(out_dir: Path = DATA_DIR, private_dir: Path = PRIVATE_DIR) -> dict:
    """Write index.json, one public <company>.json each, and one private file per pack.
    Returns {company: question count}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True)
    packs = catalog()
    written = {}
    with db.connect() as conn:
        companies = conn.execute(
            "SELECT company, count(*) AS questions FROM questions GROUP BY company ORDER BY company"
        ).fetchall()
        for c in companies:
            name = c["company"]
            for_sale = {p["function"]: pid for pid, p in packs.items() if p["company"] == name}
            stories, guides = [], []
            shown: dict[str, int] = {}
            all_stories = _company_stories(conn, name)
            for s in all_stories:
                pid = for_sale.get(s["function"])
                shown[s["function"]] = shown.get(s["function"], 0) + 1
                stories.append(s if pid is None or shown[s["function"]] <= FREE_STORIES else _teaser(s, pid))
            for fn in FUNCTIONS:
                for g in _saved_guides(name, fn):
                    if fn in for_sale:
                        g = g | {"markdown": guide_preview(g["markdown"]), "locked": for_sale[fn]}
                    guides.append(g)
            for fn, pid in for_sale.items():  # what the Worker hands to buyers of this pack
                private = {"pack": pid,
                           "experiences": [s for s in all_stories if s["function"] == fn],
                           "guides": _saved_guides(name, fn)}
                (private_dir / f"{pid}.json").write_text(json.dumps(private, default=str, separators=(",", ":")))
            data = {
                "company": name,
                "questions": _company_questions(conn, name),
                "experiences": stories,
                "guides": guides,
                "packs": [{"id": pid, **packs[pid]} for pid in for_sale.values()],
            }
            (out_dir / f"{name}.json").write_text(json.dumps(data, default=str, separators=(",", ":")))
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
