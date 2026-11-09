"""Entry point.

    prepradar init                                         # create tables, load seed tags
    prepradar ingest zemoso data/seed_urls/zemoso.txt      # fetch + extract + store (skips seen URLs)
    prepradar report zemoso [--track Backend] [--since 2023]
    prepradar ask zemoso "caching and performance" [--track Backend] [--since 2023] [-k 10]
    prepradar topics [--discovered]
"""
import argparse
from collections import defaultdict
from pathlib import Path

from prepradar.models import Category, Track

CATEGORY_ORDER = list(Category.__args__)
TRACKS = [t for t in Track.__args__ if t != "General"]


def read_urls(path: str) -> list[str]:
    return [l.strip() for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")]


def year_label(q: dict) -> str:
    if q["interview_year"]:
        return f"interviewed {q['interview_year']}"
    return f"posted {q['posted_year']}" if q["posted_year"] else ""


def print_question(q: dict, prefix: str = "   • ") -> None:
    seen = f"  ×{q['times_reported']}" if q["times_reported"] > 1 else ""
    meta = " · ".join(x for x in (", ".join(q["topics"] or []), q["track"], year_label(q)) if x)
    print(f"{prefix}{q['text']}{seen}\n       {meta}")


def cmd_init() -> None:
    from prepradar.store import db

    with db.connect() as conn:
        print(f"schema ready, {db.init(conn)} seed tags added")


def cmd_ingest(company: str, urls_file: str) -> None:
    from prepradar.extract.extractor import extract, match_tag
    from prepradar.sources.fetch import fetch
    from prepradar.store import db
    from prepradar.store.embeddings import embed

    with db.connect() as conn:
        seen = db.seen_urls(conn)
        for url in read_urls(urls_file):
            if url in seen:
                print(f"  cached ({seen[url]})  {url}")
                continue
            page = fetch(url)
            if page is None:
                print(f"  blocked/empty, will retry next run  {url}")
                continue
            firsthand, qs = extract(page, company, db.vocabulary(conn))
            posted_year = int(page.published[:4]) if page.published else None
            status = "extracted" if firsthand else "not_firsthand"
            source_id = db.add_source(conn, url, company, status, page.site, page.title, posted_year)
            if not firsthand:
                conn.commit()
                print(f"  skipped: not a firsthand candidate experience  {url}")
                continue

            vecs = embed([q.text for q in qs]) if qs else []
            dups, new_tags = 0, []
            for q, vec in zip(qs, vecs):
                qid, dup = db.add_question(conn, q, source_id, vec)
                dups += dup
                for tag in q.topics:
                    tid, name, created = db.resolve_topic(conn, tag, q.category, match_tag)
                    db.tag_question(conn, qid, tid)
                    if created:
                        new_tags.append(f"{name} ({q.category})")
                    elif name != tag:
                        print(f"      tag '{tag}' → existing '{name}'")
            conn.commit()
            print(f"  {len(qs):3d} questions, {dups} duplicates  [{page.site}]  {url}")
            for t in new_tags:
                print(f"      🆕 new tag: {t}")


def cmd_report(company: str, track: str | None, since: int | None) -> None:
    from prepradar.store import db

    with db.connect() as conn:
        questions = db.all_questions(conn, company, track, since)
    specific = [q for q in questions if q["specific"]]
    vague = [q for q in questions if not q["specific"]]
    by_cat = defaultdict(list)
    for q in specific:
        by_cat[q["category"]].append(q)

    filters = ", ".join(x for x in (f"{track} track" if track else "", f"since {since}" if since else "") if x)
    print(f"{company}" + (f" ({filters})" if filters else "") + f": {len(questions)} unique questions\n")
    for cat in CATEGORY_ORDER:
        items = sorted(by_cat.get(cat, []), key=lambda q: -q["times_reported"])
        if items:
            print(f"── {cat} ({len(items)})")
            for q in items:
                print_question(q)
            print()
    if vague:
        print(f"── Vague / not specific ({len(vague)})")
        for q in vague:
            print(f"   • {q['text']}   [{q['category']}]")


def cmd_ask(company: str, query: str, k: int, track: str | None, since: int | None) -> None:
    from prepradar.store import db
    from prepradar.store.embeddings import embed_query

    with db.connect() as conn:
        rows = db.search(conn, company, embed_query(query), k, track, since)
    print(f'"{query}" at {company}: top {len(rows)}\n')
    for q in rows:
        print_question(q, prefix=f"  {q['score']:.2f}  [{q['category']}] ")


def cmd_topics(discovered_only: bool) -> None:
    from prepradar.store import db

    with db.connect() as conn:
        rows = conn.execute(
            """SELECT t.name, t.category, t.origin, count(qt.question_id) AS n
               FROM topics t LEFT JOIN question_topics qt ON qt.topic_id = t.id
               WHERE NOT %s OR t.origin = 'discovered'
               GROUP BY t.id ORDER BY t.category, n DESC, t.name""",
            (discovered_only,),
        ).fetchall()
    cat = None
    for r in rows:
        if r["category"] != cat:
            cat = r["category"]
            print(f"\n{cat}")
        mark = "  🆕" if r["origin"] == "discovered" else ""
        print(f"  {r['n']:3d}  {r['name']}{mark}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="prepradar")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create tables and load seed tags")

    p = sub.add_parser("ingest", help="fetch URLs, extract questions, store them")
    p.add_argument("company")
    p.add_argument("urls_file")

    for name, help_ in (("report", "all questions grouped by category"), ("ask", "search questions by meaning")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("company")
        if name == "ask":
            p.add_argument("query")
            p.add_argument("-k", type=int, default=10)
        p.add_argument("--track", choices=TRACKS)
        p.add_argument("--since", type=int, help="interview (or posted) year >= this")

    p = sub.add_parser("topics", help="tag vocabulary with usage counts")
    p.add_argument("--discovered", action="store_true", help="only tags the system added")

    args = parser.parse_args()
    if args.cmd == "init":
        cmd_init()
    elif args.cmd == "ingest":
        cmd_ingest(args.company, args.urls_file)
    elif args.cmd == "report":
        cmd_report(args.company, args.track, args.since)
    elif args.cmd == "ask":
        cmd_ask(args.company, args.query, args.k, args.track, args.since)
    elif args.cmd == "topics":
        cmd_topics(args.discovered)


if __name__ == "__main__":
    main()
