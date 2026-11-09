"""Entry point.

    prepradar extract zemoso data/seed_urls/zemoso.txt   # fetch + LLM extract -> data/raw/zemoso.json
    prepradar pairs zemoso --low 0.75                    # similarity scores, to pick a dedupe threshold
    prepradar report zemoso --threshold 0.88 [--track Backend]
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from prepradar.models import ExtractedQuestion

RAW_DIR = Path("data/raw")
CATEGORY_ORDER = ["DSA", "LLD", "HLD", "Backend", "Frontend", "ML/AI", "Behavioral", "Other"]
# a Backend query should also surface Fullstack interviews, and vice versa
RELATED_TRACKS = {
    "Backend": {"Backend", "Fullstack", "General"},
    "Frontend": {"Frontend", "Fullstack", "General"},
    "Fullstack": {"Backend", "Frontend", "Fullstack", "General"},
}


def read_urls(path: str) -> list[str]:
    return [l.strip() for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")]


def load_raw(company: str) -> list[ExtractedQuestion]:
    return [ExtractedQuestion(**d) for d in json.loads((RAW_DIR / f"{company}.json").read_text())]


def cmd_extract(company: str, urls_file: str) -> None:
    from prepradar.extract.extractor import extract
    from prepradar.sources.fetch import fetch

    all_questions = []
    for url in read_urls(urls_file):
        page = fetch(url)
        if page is None:
            print(f"  skip (blocked/empty)  {url}")
            continue
        qs = extract(page, company)
        print(f"  {len(qs):3d} questions  [{page.site}, posted {page.published or '?'}]  {url}")
        all_questions.extend(qs)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{company}.json"
    out.write_text(json.dumps([q.model_dump(mode="json") for q in all_questions], indent=2))
    print(f"\n{len(all_questions)} raw questions saved to {out}")


def cmd_pairs(company: str, low: float) -> None:
    from prepradar.store.dedupe import close_pairs

    for score, a, b in close_pairs(load_raw(company), low):
        print(f"{score:.3f}  {a.text}\n       {b.text}\n")


def year_label(q: ExtractedQuestion) -> str:
    if q.interview_year:
        return f"interviewed {q.interview_year}"
    return f"posted {q.posted_year}" if q.posted_year else ""


def cmd_report(company: str, threshold: float, track: str | None) -> None:
    from prepradar.store.dedupe import dedupe

    questions = load_raw(company)
    if track:
        allowed = RELATED_TRACKS.get(track, {track, "General"})
        questions = [q for q in questions if q.track in allowed]
    merged = dedupe(questions, threshold)

    specific = [m for m in merged if m.question.specific]
    vague = [m for m in merged if not m.question.specific]
    by_cat = defaultdict(list)
    for m in specific:
        by_cat[m.question.category].append(m)

    title = f"{company}" + (f" · {track} track" if track else "")
    print(f"{title}: {len(questions)} raw → {len(merged)} unique ({len(questions) - len(merged)} duplicates merged)\n")
    for cat in CATEGORY_ORDER:
        items = sorted(by_cat.get(cat, []), key=lambda m: -m.times_reported)
        if not items:
            continue
        print(f"── {cat} ({len(items)})")
        for m in items:
            q = m.question
            seen = f"  ×{m.times_reported}" if m.times_reported > 1 else ""
            meta = " · ".join(x for x in (", ".join(q.topics), q.track, year_label(q)) if x)
            print(f"   • {q.text}{seen}\n       {meta}")
            for v in m.variants:
                print(f"       ≈ {v}")
        print()
    if vague:
        print(f"── Vague / not specific ({len(vague)})")
        for m in vague:
            print(f"   • {m.question.text}   [{m.question.category}]")


def main() -> None:
    parser = argparse.ArgumentParser(prog="prepradar")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract", help="fetch URLs and extract interview questions")
    p.add_argument("company")
    p.add_argument("urls_file")

    p = sub.add_parser("pairs", help="show similar question pairs with scores")
    p.add_argument("company")
    p.add_argument("--low", type=float, default=0.75)

    p = sub.add_parser("report", help="deduped questions grouped by category")
    p.add_argument("company")
    p.add_argument("--threshold", type=float, default=0.88)
    p.add_argument("--track", choices=["Backend", "Frontend", "Fullstack", "ML/AI", "Data", "Mobile", "QA", "DevOps", "Product"])

    args = parser.parse_args()
    if args.cmd == "extract":
        cmd_extract(args.company, args.urls_file)
    elif args.cmd == "pairs":
        cmd_pairs(args.company, args.low)
    elif args.cmd == "report":
        cmd_report(args.company, args.threshold, args.track)


if __name__ == "__main__":
    main()
