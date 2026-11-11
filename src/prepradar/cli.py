"""Entry point.

    prepradar init                                         # create tables, load seed tags
    prepradar search zemoso                                # dry run: which pages would we ingest?
    prepradar ingest zemoso [--limit 15]                   # search + fetch + extract + store (skips seen URLs)
    prepradar ingest zemoso --urls data/seed_urls/zemoso.txt
    prepradar report zemoso [--track Backend] [--since 2023]
    prepradar ask zemoso "caching and performance" [--track Backend] [--since 2023] [-k 10]
    prepradar run zemoso --track Backend                   # the LangGraph pipeline end to end
    prepradar guide zemoso --track Backend                 # grounded prep guide from stored data only
    prepradar graph                                        # Mermaid diagram of the graph
    prepradar topics [--discovered] [--merge OLD INTO] [--delete TAG]
    prepradar topics --review                              # drop generic tags, merge synonyms (LLM)
    prepradar recategorise [--company X]                   # re-sort questions under current categories
    prepradar dedupe [--company X]                         # merge near-duplicate questions (LLM)
    prepradar forget URL [URL ...]                         # drop a source wrongly accepted, and its questions
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


def find_candidates(company: str) -> list:
    from prepradar.sources.search import find_experience_urls

    return find_experience_urls(company)


def cmd_search(company: str) -> None:
    from prepradar.store import db

    with db.connect() as conn:
        seen = db.seen_urls(conn)
    results = find_candidates(company)
    print(f"{len(results)} candidate pages for {company}\n")
    for r in results:
        state = f"cached ({seen[r.url]})" if r.url in seen else "new"
        text = "has text" if r.raw_content else "no text"
        print(f"  [{state:22s}] [{text}]  {r.title[:70]}\n      {r.url}")


def cmd_ingest(company: str, urls_file: str | None, limit: int) -> None:
    from prepradar.pipeline import Candidate, ingest
    from prepradar.store import db

    if urls_file:
        candidates = [Candidate(url) for url in read_urls(urls_file)]
    else:
        candidates = [Candidate(r.url, r.title, r.raw_content) for r in find_candidates(company)]
        print(f"search found {len(candidates)} candidate pages")
    with db.connect() as conn:
        ingest(conn, company, candidates, limit)


def print_report(questions: list[dict], header: str) -> None:
    specific = [q for q in questions if q["specific"]]
    vague = [q for q in questions if not q["specific"]]
    by_cat = defaultdict(list)
    for q in specific:
        by_cat[q["category"]].append(q)

    print(f"{header}: {len(questions)} unique questions\n")
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


def report_header(company: str, track: str | None, since: int | None) -> str:
    filters = ", ".join(x for x in (f"{track} track" if track else "", f"since {since}" if since else "") if x)
    return company + (f" ({filters})" if filters else "")


def cmd_report(company: str, track: str | None, since: int | None) -> None:
    from prepradar.store import db

    with db.connect() as conn:
        questions = db.all_questions(conn, company, track, since)
    print_report(questions, report_header(company, track, since))


def save_guide(company: str, track: str | None, md: str) -> Path:
    out = Path("reports") / (company + (f"-{track.lower().replace('/', '-')}" if track else "") + ".md")
    out.parent.mkdir(exist_ok=True)
    out.write_text(md)
    return out


def cmd_run(company: str, track: str | None, since: int | None, limit: int, refresh: bool,
            list_only: bool) -> None:
    from prepradar.graph.build import build

    graph = build()
    inputs = {"company": company, "track": track, "since": since, "limit": limit, "refresh": refresh,
              "with_guide": not list_only}
    final: dict = {}
    # stream_mode="updates" yields {node_name: fields_it_returned} after each node
    for update in graph.stream(inputs, stream_mode="updates"):
        for node, changes in update.items():
            for line in changes.get("log", []):
                print(f"▶ {line}")
            final.update(changes)
    gaps = final.get("gaps") or []
    if gaps:
        print(f"\n⚠ still thin after searching: {', '.join(gaps)} (few candidates write these rounds up)")
    print()
    if final.get("guide_md"):
        print(final["guide_md"])
        print(f"saved {save_guide(company, track, final['guide_md'])}")
    else:
        print_report(final.get("questions", []), report_header(company, track, since))


def cmd_guide(company: str, track: str | None, since: int | None) -> None:
    from prepradar.report.writer import render_markdown, write_guide
    from prepradar.store import db

    with db.connect() as conn:
        questions = db.all_questions(conn, company, track, since)
    if not questions:
        raise RuntimeError(f"no questions stored for {company}; run `prepradar run {company}` first")
    md = render_markdown(company, track, write_guide(company, track, questions))
    print(md)
    print(f"saved {save_guide(company, track, md)}")


def cmd_graph() -> None:
    from prepradar.graph.build import build

    print(build().get_graph().draw_mermaid())


def cmd_ask(company: str, query: str, k: int, track: str | None, since: int | None) -> None:
    from prepradar.store import db
    from prepradar.store.embeddings import embed_query

    with db.connect() as conn:
        rows = db.search(conn, company, embed_query(query), k, track, since)
    print(f'"{query}" at {company}: top {len(rows)}\n')
    for q in rows:
        print_question(q, prefix=f"  {q['score']:.2f}  [{q['category']}] ")


def cmd_topics(discovered_only: bool, merge: list[str] | None, delete: str | None, review: bool) -> None:
    from prepradar.store import db

    if review:
        cmd_review_tags()
        return
    with db.connect() as conn:
        if merge:
            print(f"merged '{merge[0]}' into '{merge[1]}' ({db.merge_topic(conn, *merge)} questions moved)")
            return
        if delete:
            db.delete_topic(conn, delete)
            print(f"deleted tag '{delete}'")
            return
        rows = conn.execute(
            f"""SELECT t.name, t.category, t.origin, count(qt.question_id) AS n,
                       {db.TAG_SOURCES} AS sources
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
        mark = ""
        if r["origin"] == "discovered":
            mark = "  🆕" if r["sources"] >= db.MIN_TAG_SOURCES else "  (provisional: 1 source)"
        print(f"  {r['n']:3d}  {r['name']}{mark}")


def cmd_recategorise(company: str | None) -> None:
    from prepradar.extract.extractor import recategorise
    from prepradar.store import db

    batch = 25  # questions per LLM call; small batches keep answers aligned with ids
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, text, category FROM questions WHERE %s::text IS NULL OR company = %s ORDER BY id",
            (company, company),
        ).fetchall()
        moves = 0
        for i in range(0, len(rows), batch):
            chunk = rows[i:i + batch]
            new = recategorise(chunk)
            for r in chunk:
                cat = new.get(r["id"])
                if cat and cat != r["category"]:
                    conn.execute("UPDATE questions SET category = %s WHERE id = %s", (cat, r["id"]))
                    print(f"  {r['category']:>14} → {cat:<14} {r['text'][:80]}")
                    moves += 1
        conn.commit()
        tags = db.sync_tag_categories(conn)
    print(f"{moves} of {len(rows)} questions moved; {tags} tags followed their questions")


def cmd_dedupe(company: str | None) -> None:
    from prepradar.extract.extractor import same_question
    from prepradar.store import db

    with db.connect() as conn:
        pairs = db.near_duplicate_pairs(conn, company)
        gone: set[int] = set()
        merged = 0
        for p in pairs:
            if p["a"] in gone or p["b"] in gone:
                continue  # one side was already merged away
            if same_question(p["b_text"], [p["a_text"]]) == 0:
                db.merge_questions(conn, keep=p["a"], drop=p["b"])  # keep the older one
                gone.add(p["b"])
                merged += 1
                print(f"  merged ({p['sim']:.3f})  {p['a_text'][:60]}  ⇐  {p['b_text'][:60]}")
        conn.commit()
    print(f"{merged} duplicates merged out of {len(pairs)} close pairs checked")


def cmd_review_tags() -> None:
    from prepradar.extract.extractor import match_tag
    from prepradar.models import GENERIC_TAG
    from prepradar.store import db

    with db.connect() as conn:
        tags = conn.execute(
            "SELECT name, category FROM topics WHERE origin = 'discovered' ORDER BY name"
        ).fetchall()
        dropped = merged = 0
        for t in tags:
            others = [r["name"] for r in conn.execute(
                "SELECT name FROM topics WHERE category = %s AND name <> %s", (t["category"], t["name"]))]
            verdict = match_tag(t["name"], others)
            if verdict == GENERIC_TAG:
                db.delete_topic(conn, t["name"])
                dropped += 1
                print(f"  dropped (generic)  {t['name']}")
            elif verdict:
                db.merge_topic(conn, t["name"], verdict)
                merged += 1
                print(f"  merged  {t['name']} → {verdict}")
    print(f"{len(tags)} discovered tags reviewed: {dropped} dropped, {merged} merged")


def cmd_forget(urls: list[str]) -> None:
    from prepradar.store import db

    with db.connect() as conn:
        for url in urls:
            print(f"forgot {url}: {db.forget_source(conn, url)} questions removed")


def main() -> None:
    parser = argparse.ArgumentParser(prog="prepradar")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create tables and load seed tags")

    p = sub.add_parser("search", help="list candidate pages without extracting")
    p.add_argument("company")

    p = sub.add_parser("ingest", help="find pages, extract questions, store them")
    p.add_argument("company")
    p.add_argument("--urls", dest="urls_file", help="use a URL list instead of web search")
    p.add_argument("--limit", type=int, default=15, help="max new pages sent to the LLM this run")

    for name, help_ in (("report", "all questions grouped by category"), ("ask", "search questions by meaning")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("company")
        if name == "ask":
            p.add_argument("query")
            p.add_argument("-k", type=int, default=10)
        p.add_argument("--track", choices=TRACKS)
        p.add_argument("--since", type=int, help="interview (or posted) year >= this")

    p = sub.add_parser("run", help="full pipeline as a LangGraph: cache → search → ingest → coverage loop → report")
    p.add_argument("company")
    p.add_argument("--track", choices=TRACKS)
    p.add_argument("--since", type=int)
    p.add_argument("--limit", type=int, default=10, help="max new pages per search round")
    p.add_argument("--refresh", action="store_true", help="search even if cached data is sufficient")
    p.add_argument("--list", dest="list_only", action="store_true",
                   help="print the raw question list instead of the LLM-written guide")

    p = sub.add_parser("guide", help="LLM-written prep guide from stored questions (no searching)")
    p.add_argument("company")
    p.add_argument("--track", choices=TRACKS)
    p.add_argument("--since", type=int)

    sub.add_parser("graph", help="print the pipeline graph as a Mermaid diagram")

    p = sub.add_parser("topics", help="tag vocabulary with usage counts")
    p.add_argument("--discovered", action="store_true", help="only tags the system added")
    p.add_argument("--merge", nargs=2, metavar=("OLD", "INTO"), help="fold tag OLD into tag INTO")
    p.add_argument("--delete", metavar="TAG", help="remove a tag from the vocabulary and all questions")
    p.add_argument("--review", action="store_true", help="LLM-review discovered tags: drop generic, merge synonyms")

    p = sub.add_parser("recategorise", help="re-sort stored questions under the current category rules")
    p.add_argument("--company")

    p = sub.add_parser("dedupe", help="merge stored near-duplicate questions (LLM-judged)")
    p.add_argument("--company")

    p = sub.add_parser("forget", help="drop a source wrongly accepted as firsthand, and its questions")
    p.add_argument("urls", nargs="+")

    args = parser.parse_args()
    try:
        run(args)
    except RuntimeError as e:  # config problems like a missing API key
        raise SystemExit(f"error: {e}")


def run(args: argparse.Namespace) -> None:
    if args.cmd == "init":
        cmd_init()
    elif args.cmd == "search":
        cmd_search(args.company)
    elif args.cmd == "ingest":
        cmd_ingest(args.company, args.urls_file, args.limit)
    elif args.cmd == "report":
        cmd_report(args.company, args.track, args.since)
    elif args.cmd == "ask":
        cmd_ask(args.company, args.query, args.k, args.track, args.since)
    elif args.cmd == "run":
        cmd_run(args.company, args.track, args.since, args.limit, args.refresh, args.list_only)
    elif args.cmd == "guide":
        cmd_guide(args.company, args.track, args.since)
    elif args.cmd == "graph":
        cmd_graph()
    elif args.cmd == "topics":
        cmd_topics(args.discovered, args.merge, args.delete, args.review)
    elif args.cmd == "recategorise":
        cmd_recategorise(args.company)
    elif args.cmd == "dedupe":
        cmd_dedupe(args.company)
    elif args.cmd == "forget":
        cmd_forget(args.urls)


if __name__ == "__main__":
    main()
