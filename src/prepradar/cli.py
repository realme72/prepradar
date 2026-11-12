"""Entry point.

    prepradar init                                         # create tables, load seed tags
    prepradar search zemoso                                # dry run: which pages would we ingest?
    prepradar ingest zemoso [--limit 15]                   # search + fetch + extract + store (skips seen URLs)
    prepradar ingest zemoso --urls data/seed_urls/zemoso.txt
    prepradar report zemoso [--track Backend] [--since 2023]
    prepradar ask zemoso "caching and performance" [--track Backend] [--since 2023] [-k 10]
    prepradar run zemoso --track Backend                   # the LangGraph pipeline end to end
    prepradar run amazon --function Product --position "Product Manager"
    prepradar guide zemoso --track Backend                 # grounded prep guide from stored data only
    prepradar graph                                        # Mermaid diagram of the graph
    prepradar topics [--discovered] [--merge OLD INTO] [--delete TAG]
    prepradar topics --review                              # drop generic tags, merge synonyms (LLM)
    prepradar recategorise [--company X]                   # re-sort questions under current categories
    prepradar reposition                                   # fill function/position from role titles (LLM)
    prepradar dedupe [--company X]                         # merge near-duplicate questions (LLM)
    prepradar recheck [--company X]                        # re-run the firsthand check, drop failures
    prepradar forget URL [URL ...]                         # drop a source wrongly accepted, and its questions
"""
import argparse
from collections import defaultdict
from pathlib import Path

from prepradar.roles import CATEGORIES, FUNCTIONS, TRACKS, Scope

CATEGORY_ORDER = CATEGORIES


def read_urls(path: str) -> list[str]:
    return [l.strip() for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")]


def year_label(q: dict) -> str:
    if q["interview_year"]:
        return f"interviewed {q['interview_year']}"
    return f"posted {q['posted_year']}" if q["posted_year"] else ""


def print_question(q: dict, prefix: str = "   • ") -> None:
    seen = f"  ×{q['times_reported']}" if q["times_reported"] > 1 else ""
    meta = " · ".join(x for x in (", ".join(q["topics"] or []), q["position"], year_label(q)) if x)
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


def cmd_paste(company: str, url: str, path: str | None) -> None:
    """Ingest a write-up from text a person copied, for sites that refuse automated
    reading (LeetCode Discuss). Same checks as any page: firsthand, dedupe, tags, story.
    The text itself isn't stored, only what's extracted, with the URL as the source."""
    import sys

    from prepradar.pipeline import Candidate, ingest
    from prepradar.store import db

    text = Path(path).read_text() if path else sys.stdin.read()
    if len(text.strip()) < 300:
        raise RuntimeError("that's too little text for a write-up; copy the whole post")
    with db.connect() as conn:
        stats = ingest(conn, company, [Candidate(url, None, text)], limit=1)
    if stats.pages == 0 and stats.rejected == 0:
        print("nothing added (already stored, or the same post as one we have)")


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


def report_header(scope: Scope) -> str:
    return f"{scope.company} ({scope.label()})"


def cmd_report(scope: Scope) -> None:
    from prepradar.store import db

    with db.connect() as conn:
        questions = db.all_questions(conn, scope)
    print_report(questions, report_header(scope))


def save_guide(scope: Scope, md: str) -> str:
    from prepradar.store import db

    with db.connect() as conn:
        db.save_guide(conn, scope, md)
    return f"guide {scope.slug()}"


def cmd_import_guides(folder: Path) -> None:
    """One-off: guides used to be saved as reports/<slug>.md. Load those into the
    guides table (a file whose guide is already there is skipped)."""
    from datetime import date

    from prepradar.roles import UNKNOWN
    from prepradar.store import db

    files = {p.stem: p for p in folder.glob("*.md")}
    years = [None] + [date.today().year - n for n in range(1, 11)]
    added = 0
    with db.connect() as conn:
        companies = [r["company"] for r in conn.execute("SELECT DISTINCT company FROM questions")]
        # a slug can't be split back into its parts ("jp-morgan-engineering"), so
        # generate every scope and look its slug up
        for company in companies:
            for fn, f in FUNCTIONS.items():
                for pos in [None] + f.positions + [UNKNOWN]:
                    for track in [None] + (TRACKS if fn == "Engineering" else []):
                        for since in years:
                            scope = Scope(company, fn, pos, track, since)
                            path = files.pop(scope.slug(), None)
                            if path and db.guide(conn, scope) is None:
                                db.save_guide(conn, scope, path.read_text())
                                added += 1
    print(f"imported {added} guides" + (f"; no matching scope for: {', '.join(sorted(files))}" if files else ""))


def cmd_count(company: str) -> None:
    """Prints how many questions a company has (the collect workflow checks for 0)."""
    from prepradar.store import db

    with db.connect() as conn:
        print(conn.execute("SELECT count(*) AS n FROM questions WHERE company = %s", (company,)).fetchone()["n"])


def cmd_run(scope: Scope, limit: int, refresh: bool, list_only: bool) -> None:
    from prepradar.graph.build import build

    graph = build()
    inputs = {"scope": scope, "limit": limit, "refresh": refresh, "with_guide": not list_only}
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
        print(f"saved {save_guide(scope, final['guide_md'])}")
    else:
        print_report(final.get("questions", []), report_header(scope))


def cmd_guide(scope: Scope) -> None:
    from prepradar.report.writer import render_markdown, write_guide
    from prepradar.store import db

    with db.connect() as conn:
        questions = db.all_questions(conn, scope)
    if not questions:
        raise RuntimeError(f"no questions stored for {scope.label()} at {scope.company}; "
                           f"run `prepradar run {scope.company}` first")
    md = render_markdown(scope, write_guide(scope, questions))
    print(md)
    print(f"saved {save_guide(scope, md)}")


def cmd_graph() -> None:
    from prepradar.graph.build import build

    print(build().get_graph().draw_mermaid())


def cmd_ask(scope: Scope, query: str, k: int) -> None:
    from prepradar.store import db
    from prepradar.store.embeddings import embed_query

    with db.connect() as conn:
        rows = db.search(conn, scope, embed_query(query), k)
    print(f'"{query}" at {scope.company} ({scope.label()}): top {len(rows)}\n')
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


def cmd_respecify(company: str | None) -> None:
    """Re-judge every stored DSA question under DSA_SPECIFIC_RULE, in both directions:
    "solve array and hashmap problems" becomes vague, a named problem becomes specific."""
    from prepradar.extract.extractor import vague_dsa
    from prepradar.store import db

    batch = 25
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT id, text, specific FROM questions WHERE category = 'DSA'
               AND (%s::text IS NULL OR company = %s) ORDER BY id""",
            (company, company),
        ).fetchall()
        vague: set[int] = set()
        for i in range(0, len(rows), batch):
            vague |= vague_dsa(rows[i:i + batch])
        changed = 0
        for r in rows:
            specific = r["id"] not in vague
            if specific != r["specific"]:
                conn.execute("UPDATE questions SET specific = %s WHERE id = %s", (specific, r["id"]))
                print(f"  {'specific' if specific else 'vague':>8}: {r['text'][:100]}")
                changed += 1
        conn.commit()
    print(f"{len(rows)} DSA questions: {len(rows) - len(vague)} specific, {len(vague)} vague ({changed} changed)")


def cmd_reposition() -> None:
    """Fill function/position from the role titles candidates wrote (and the old
    engineering-only track), for questions stored before roles.py existed or after
    a ladder changes."""
    from prepradar.extract.extractor import place_roles
    from prepradar.roles import engineering_level
    from prepradar.store import db

    with db.connect() as conn:
        titles = [r["role"] for r in conn.execute(
            "SELECT DISTINCT role FROM questions WHERE role IS NOT NULL ORDER BY role")]
        placed = place_roles(titles)
        for title, (function, position) in placed.items():
            if function == "Engineering":
                position = engineering_level(title)
            conn.execute("UPDATE questions SET function = %s, position = %s WHERE role = %s",
                         (function, position, title))
            print(f"  {title:45} → {function} · {position}")
        # untitled rows: the old "Data" track meant the data function
        conn.execute("UPDATE questions SET function = 'Data' WHERE role IS NULL AND track = 'Data'")
        # tracks are engineering specialties now
        conn.execute("UPDATE questions SET track = 'General' WHERE function <> 'Engineering' OR NOT track = ANY(%s)",
                     (TRACKS,))
        conn.commit()
    print(f"{len(placed)} of {len(titles)} role titles placed")


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


def cmd_recheck(company: str | None) -> None:
    """Re-run the firsthand check on every accepted source; forget the ones it now rejects."""
    from prepradar.extract.extractor import classify
    from prepradar.sources.fetch import load_page
    from prepradar.store import db

    with db.connect() as conn:
        rows = conn.execute(
            """SELECT url, company, title FROM sources WHERE status = 'extracted'
               AND (%s::text IS NULL OR company = %s) ORDER BY company, id""",
            (company, company),
        ).fetchall()
        dropped = unreadable = 0
        for r in rows:
            page = load_page(r["url"], r["title"], None)
            if page is None:
                unreadable += 1  # can't re-read it now (blocked, deleted); keep what we have
                continue
            check = classify(page, r["company"])
            if not check.is_firsthand:
                removed = db.forget_source(conn, r["url"])
                dropped += 1
                print(f"  dropped ({check.page_kind}, {removed} questions)  {r['url']}")
    print(f"{len(rows)} sources rechecked: {dropped} dropped, {unreadable} couldn't be fetched (kept)")


def cmd_experiences(company: str | None, redo: bool) -> None:
    """Backfill candidate stories for sources ingested before experiences existed. Page
    text isn't stored (it would keep people's names), so each page is fetched again;
    pages longer than the old 15k-character cut-off also get their remaining questions."""
    from prepradar import config
    from prepradar.extract.extractor import extract_experiences, extract_questions
    from prepradar.pipeline import store_questions
    from prepradar.sources.fetch import load_page
    from prepradar.store import db

    with db.connect() as conn:
        rows = conn.execute(
            """SELECT s.id, s.url, s.company, s.title, s.posted_year FROM sources s
               WHERE s.status = 'extracted' AND (%s::text IS NULL OR s.company = %s)
                 AND (%s OR NOT EXISTS (SELECT 1 FROM experiences e WHERE e.source_id = s.id))
               ORDER BY s.company, s.id""",
            (company, company, redo),
        ).fetchall()
        stories = extra = unreadable = 0
        for r in rows:
            page = load_page(r["url"], r["title"], None)
            if page is None:
                unreadable += 1
                print(f"  couldn't fetch, skipped  {r['url']}")
                continue
            exps = extract_experiences(page, r["company"])
            db.add_experiences(conn, r["id"], r["company"], r["posted_year"], exps)
            note = ""
            if len(page.text) > config.MAX_PAGE_CHARS:
                qs = extract_questions(page, r["company"], db.vocabulary(conn), first_chunk=1)
                dups, _, _ = store_questions(conn, qs, r["id"])
                extra += len(qs) - dups
                note = f", {len(qs) - dups} new questions past the old cut-off"
            conn.commit()
            stories += len(exps)
            print(f"  {len(exps):2d} experiences{note}  {r['url']}")
    print(f"{len(rows)} sources: {stories} experiences, {extra} more questions, "
          f"{unreadable} couldn't be fetched")


def cmd_dates(company: str | None) -> None:
    """Backfill sources' publish dates (posted_on), stored only as a year before. Reads
    each page's metadata again: no model calls. Pages that give no date stay without one."""
    from prepradar.sources.fetch import fetch, paste_only
    from prepradar.store import db

    with db.connect() as conn:
        rows = conn.execute(
            """SELECT id, url FROM sources WHERE status = 'extracted' AND posted_on IS NULL
                 AND (%s::text IS NULL OR company = %s) ORDER BY id""",
            (company, company),
        ).fetchall()
        found = 0
        for r in rows:
            page = None if paste_only(r["url"]) else fetch(r["url"])
            posted_on = db.posted_date(page.published if page else None)
            if posted_on is None:
                continue
            conn.execute("UPDATE sources SET posted_on = %s, posted_year = %s WHERE id = %s",
                         (posted_on, posted_on.year, r["id"]))
            # rows stored without a year get this one (the year filter uses it)
            conn.execute("UPDATE experiences SET posted_year = %s WHERE source_id = %s AND posted_year IS NULL",
                         (posted_on.year, r["id"]))
            conn.execute(
                """UPDATE questions q SET posted_year = %s FROM question_sources s
                   WHERE s.question_id = q.id AND s.source_id = %s AND q.posted_year IS NULL""",
                (posted_on.year, r["id"]))
            conn.commit()
            found += 1
            print(f"  {posted_on:%b %Y}  {r['url']}")
    print(f"{found} of {len(rows)} sources dated")


def cmd_usage(days: int) -> None:
    """Tokens per model and purpose, from the llm_usage log. Calls made before the log
    existed aren't in it; the OpenAI dashboard has the full history and the cost."""
    from prepradar.store import db

    with db.connect() as conn:
        rows = conn.execute(
            """SELECT model, purpose, count(*) AS calls, sum(input_tokens) AS input,
                      sum(cached_tokens) AS cached, sum(output_tokens) AS output,
                      sum(reasoning_tokens) AS reasoning
               FROM llm_usage WHERE at > now() - make_interval(days => %s)
               GROUP BY 1, 2 ORDER BY 1, sum(input_tokens) DESC""",
            (days,),
        ).fetchall()
    if not rows:
        print(f"no LLM calls logged in the last {days} days")
        return
    print(f"OpenAI tokens, last {days} days (output includes reasoning)\n")
    print(f"{'model':<16} {'purpose':<14} {'calls':>6} {'input':>11} {'cached':>9} {'output':>9} {'reasoning':>10}")
    for r in rows:
        print(f"{r['model']:<16} {r['purpose']:<14} {r['calls']:>6} {r['input']:>11,} {r['cached']:>9,} "
              f"{r['output']:>9,} {r['reasoning']:>10,}")
    print(f"\n{'total':<31} {sum(r['calls'] for r in rows):>6} {sum(r['input'] for r in rows):>11,} "
          f"{sum(r['cached'] for r in rows):>9,} {sum(r['output'] for r in rows):>9,} "
          f"{sum(r['reasoning'] for r in rows):>10,}")
    print("\nCost in dollars: https://platform.openai.com/usage")


def cmd_export() -> None:
    from prepradar.publish import DATA_DIR, export

    written = export()
    total = sum(written.values())
    print(f"exported {len(written)} companies ({total} questions) to {DATA_DIR.relative_to(Path.cwd())}")


def cmd_forget(urls: list[str]) -> None:
    from prepradar.store import db

    with db.connect() as conn:
        for url in urls:
            print(f"forgot {url}: {db.forget_source(conn, url)} questions removed")


def add_scope_args(p) -> None:
    p.add_argument("--function", default="Engineering", choices=list(FUNCTIONS))
    p.add_argument("--position", help="a rung on the function's ladder, e.g. 'SDE 2', 'Product Manager'")
    p.add_argument("--track", choices=TRACKS, help="engineering specialty")
    p.add_argument("--since", type=int, help="interview (or posted) year >= this")


def scope_from(args) -> Scope:
    try:
        return Scope(args.company, args.function, args.position, args.track, args.since)
    except ValueError as e:
        raise SystemExit(f"error: {e}")


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
        add_scope_args(p)

    p = sub.add_parser("run", help="full pipeline as a LangGraph: cache → search → ingest → coverage loop → report")
    p.add_argument("company")
    add_scope_args(p)
    p.add_argument("--limit", type=int, default=10, help="max new pages per search round")
    p.add_argument("--refresh", action="store_true", help="search even if cached data is sufficient")
    p.add_argument("--list", dest="list_only", action="store_true",
                   help="print the raw question list instead of the LLM-written guide")

    p = sub.add_parser("guide", help="LLM-written prep guide from stored questions (no searching)")
    p.add_argument("company")
    add_scope_args(p)

    sub.add_parser("graph", help="print the pipeline graph as a Mermaid diagram")

    p = sub.add_parser("topics", help="tag vocabulary with usage counts")
    p.add_argument("--discovered", action="store_true", help="only tags the system added")
    p.add_argument("--merge", nargs=2, metavar=("OLD", "INTO"), help="fold tag OLD into tag INTO")
    p.add_argument("--delete", metavar="TAG", help="remove a tag from the vocabulary and all questions")
    p.add_argument("--review", action="store_true", help="LLM-review discovered tags: drop generic, merge synonyms")

    p = sub.add_parser("recategorise", help="re-sort stored questions under the current category rules")
    p.add_argument("--company")

    p = sub.add_parser("respecify", help="re-judge which DSA questions name an actual problem (others go to vague reports)")
    p.add_argument("--company")

    sub.add_parser("reposition", help="fill function/position on stored questions from their role titles")

    p = sub.add_parser("dedupe", help="merge stored near-duplicate questions (LLM-judged)")
    p.add_argument("--company")

    p = sub.add_parser("recheck", help="re-run the firsthand check on accepted sources; forget failures")
    p.add_argument("--company")

    p = sub.add_parser("forget", help="drop a source wrongly accepted as firsthand, and its questions")
    p.add_argument("urls", nargs="+")

    p = sub.add_parser("experiences", help="extract candidate stories (rounds, outcome, tips) for stored sources")
    p.add_argument("--company")
    p.add_argument("--redo", action="store_true", help="re-extract sources that already have stories")

    p = sub.add_parser("paste", help="add a write-up from copied text (for sites like LeetCode that block reading)")
    p.add_argument("company")
    p.add_argument("url", help="the post's address, kept as the source link")
    p.add_argument("--file", help="read the text from a file instead of stdin")

    sub.add_parser("export", help="write the static site's data (web/public/data/*.json)")
    p = sub.add_parser("import-guides", help="one-off: load old reports/*.md guide files into the database")
    p.add_argument("folder", nargs="?", default="reports", type=Path)
    p = sub.add_parser("count", help="number of questions stored for a company")
    p.add_argument("company")

    p = sub.add_parser("dates", help="backfill write-ups' publish dates (month) from page metadata")
    p.add_argument("--company")

    p = sub.add_parser("usage", help="OpenAI tokens used, per model and purpose")
    p.add_argument("--days", type=int, default=30)

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
        cmd_report(scope_from(args))
    elif args.cmd == "ask":
        cmd_ask(scope_from(args), args.query, args.k)
    elif args.cmd == "run":
        cmd_run(scope_from(args), args.limit, args.refresh, args.list_only)
    elif args.cmd == "guide":
        cmd_guide(scope_from(args))
    elif args.cmd == "graph":
        cmd_graph()
    elif args.cmd == "topics":
        cmd_topics(args.discovered, args.merge, args.delete, args.review)
    elif args.cmd == "recategorise":
        cmd_recategorise(args.company)
    elif args.cmd == "respecify":
        cmd_respecify(args.company)
    elif args.cmd == "reposition":
        cmd_reposition()
    elif args.cmd == "dedupe":
        cmd_dedupe(args.company)
    elif args.cmd == "recheck":
        cmd_recheck(args.company)
    elif args.cmd == "forget":
        cmd_forget(args.urls)
    elif args.cmd == "experiences":
        cmd_experiences(args.company, args.redo)
    elif args.cmd == "paste":
        cmd_paste(args.company, args.url, args.file)
    elif args.cmd == "export":
        cmd_export()
    elif args.cmd == "import-guides":
        cmd_import_guides(args.folder)
    elif args.cmd == "count":
        cmd_count(args.company.strip().lower())
    elif args.cmd == "dates":
        cmd_dates(args.company and args.company.strip().lower())
    elif args.cmd == "usage":
        cmd_usage(args.days)


if __name__ == "__main__":
    main()
