"""Entry point.

    prepradar extract zemoso data/seed_urls/zemoso.txt
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from prepradar.extract.extractor import extract
from prepradar.sources.fetch import fetch

RAW_DIR = Path("data/raw")


def read_urls(path: str) -> list[str]:
    return [l.strip() for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")]


def cmd_extract(company: str, urls_file: str) -> None:
    all_questions = []
    for url in read_urls(urls_file):
        page = fetch(url)
        if page is None:
            print(f"  skip (blocked/empty)  {url}")
            continue
        qs = extract(page, company)
        print(f"  {len(qs):3d} questions  [{page.site}]  {url}")
        all_questions.extend(qs)

    by_cat = defaultdict(list)
    for q in all_questions:
        by_cat[q.category].append(q)
    print(f"\n{len(all_questions)} questions total\n")
    for cat, qs in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        print(f"── {cat} ({len(qs)})")
        for q in qs:
            meta = ", ".join(str(x) for x in (q.round, q.role, q.year) if x and x != "Unknown")
            print(f"   • {q.text}  [{meta}]" if meta else f"   • {q.text}")
        print()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{company}.json"
    out.write_text(json.dumps([q.model_dump(mode="json") for q in all_questions], indent=2))
    print(f"saved {out}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="prepradar")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract", help="fetch URLs and extract interview questions")
    p.add_argument("company")
    p.add_argument("urls_file")
    args = parser.parse_args()
    if args.cmd == "extract":
        cmd_extract(args.company, args.urls_file)


if __name__ == "__main__":
    main()
