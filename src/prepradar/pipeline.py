"""Ingest candidate pages: fetch -> extract -> same-post check -> store -> tag -> experiences.

Pages are read INGEST_WORKERS at a time (fetching and the AI calls, which are almost all
of the time); each is then saved one by one. Shared by `prepradar ingest` and the
graph's ingest node.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from prepradar import config
from prepradar.extract.extractor import classify, extract_experiences, extract_questions, match_tag, same_question
from prepradar.models import ExperienceDraft, ExtractedQuestion, Page
from prepradar.sources.fetch import load_page, paste_only
from prepradar.store import db
from prepradar.store.embeddings import embed


@dataclass
class Candidate:
    url: str
    title: str | None = None
    raw_text: str | None = None  # page text from the search provider, if any


@dataclass
class IngestStats:
    pages: int = 0          # new firsthand pages extracted
    rejected: int = 0       # new pages the classifier turned away
    questions: int = 0      # questions extracted
    new_questions: int = 0  # questions that weren't duplicates
    experiences: int = 0    # candidate stories extracted
    new_tags: list[str] = field(default_factory=list)


@dataclass
class Read:
    """One page after the parallel part: fetched, checked and extracted, nothing saved."""
    page: Page | None
    firsthand: bool = False
    questions: list[ExtractedQuestion] = field(default_factory=list)
    experiences: list[ExperienceDraft] = field(default_factory=list)


def store_questions(conn, qs, source_id: int) -> tuple[int, list[str], dict[str, str]]:
    """Embed, dedupe and tag extracted questions. Returns (duplicates, new tags, tags
    mapped onto existing ones)."""
    judge = prejudge_tags(conn, qs)
    vecs = embed([q.text for q in qs]) if qs else []
    dups, new_tags, mapped = 0, [], {}
    for q, vec in zip(qs, vecs):
        qid, dup = db.add_question(conn, q, source_id, vec, same_question)
        dups += dup
        for tag in q.topics:
            resolved = db.resolve_topic(conn, tag, q.category, judge)
            if resolved is None:
                continue
            tid, name, created = resolved
            db.tag_question(conn, qid, tid)
            if created:
                new_tags.append(f"{name} ({q.category})")
            elif name != tag:
                mapped[tag] = name
    return dups, new_tags, mapped


def prejudge_tags(conn, qs):
    """Ask the tag judge about all of a page's new tags at once, in parallel (one at a
    time, these calls were half of a collection's time). Returns a judge for
    resolve_topic that answers from these results; a question it wasn't asked (the
    candidates changed because an earlier tag on the page created one) goes to the
    model as before."""
    asks = {}
    for q in qs:
        for tag in q.topics:
            if (tag, q.category) not in asks:
                asks[(tag, q.category)] = db.judge_input(conn, tag, q.category)
    asks = {(tag, tuple(cands)) for (tag, _), cands in asks.items() if cands is not None}
    with ThreadPoolExecutor(max_workers=8) as pool:
        answers = dict(zip(asks, pool.map(lambda a: match_tag(a[0], list(a[1])), asks)))

    def judge(name: str, candidates: list[str]):
        key = (name, tuple(candidates))
        return answers[key] if key in answers else match_tag(name, candidates)
    return judge


def read_page(c: Candidate, company: str, vocabulary: dict[str, str]) -> Read:
    """The slow part of ingesting a page, safe to run in parallel: it touches no database.
    The question and story extractions run side by side once the page is accepted."""
    page = load_page(c.url, c.title, c.raw_text)
    if page is None or not classify(page, company).is_firsthand:
        return Read(page)
    with ThreadPoolExecutor(max_workers=2) as pool:
        qs = pool.submit(extract_questions, page, company, vocabulary)
        exps = pool.submit(extract_experiences, page, company)
        return Read(page, True, qs.result(), exps.result())


def ingest(conn, company: str, candidates: list[Candidate], limit: int) -> IngestStats:
    stats = IngestStats()
    seen = db.seen_urls(conn)
    todo = []
    for c in candidates:
        if c.url in seen:
            print(f"  cached ({seen[c.url]})  {c.url}")
        elif c.url not in {t.url for t in todo}:
            todo.append(c)

    with ThreadPoolExecutor(max_workers=config.INGEST_WORKERS) as pool:
        # Only accepted pages count: rejecting one is a small classifier call, and
        # counting rejects let a batch of prep guides use up the whole budget. So pages
        # go in waves no bigger than what's left of the limit, and never past it.
        while todo and stats.pages < limit:
            n = min(config.INGEST_WORKERS, limit - stats.pages)
            wave, todo = todo[:n], todo[n:]
            vocabulary = db.vocabulary(conn)
            reads = list(pool.map(lambda c: read_page(c, company, vocabulary), wave))
            for c, r in zip(wave, reads):
                save(conn, company, c, r, stats)
    if todo:
        print(f"  limit of {limit} new write-ups reached; run again for the rest")
    return stats


def save(conn, company: str, c: Candidate, r: Read, stats: IngestStats) -> None:
    page = r.page
    if page is None and paste_only(c.url):
        print(f"  can't be read automatically; to add it, copy the post and run "
              f"`pbpaste | uv run prepradar paste {company} '{c.url}'`")
        return
    if page is None:
        print(f"  blocked/empty, will retry next run  {c.url}")
        return
    posted_on = db.posted_date(page.published)
    # checked here, not before reading: two URLs of one post can be in the same wave
    same = db.find_same_post(conn, company, page.text, page.title)
    if same:
        db.add_source(conn, c.url, company, "duplicate", page.site, page.title, posted_on, page.text)
        conn.commit()
        print(f"  same post as {same}, skipped  {c.url}")
        return
    status = "extracted" if r.firsthand else "not_firsthand"
    source_id = db.add_source(conn, c.url, company, status, page.site, page.title, posted_on, page.text)
    if not r.firsthand:
        stats.rejected += 1
        conn.commit()
        print(f"  skipped: not a firsthand candidate experience  {c.url}")
        return
    stats.pages += 1

    qs, exps = r.questions, r.experiences
    dups, new_tags, mapped = store_questions(conn, qs, source_id)
    db.add_experiences(conn, source_id, company, posted_on and posted_on.year, exps)
    conn.commit()
    stats.experiences += len(exps)
    stats.questions += len(qs)
    stats.new_questions += len(qs) - dups
    stats.new_tags += new_tags
    print(f"  {len(qs):3d} questions, {dups} duplicates, {len(exps)} experiences  [{page.site}]  {c.url}")
    if mapped:
        print("      tags mapped: " + ", ".join(f"{a} → {b}" for a, b in mapped.items()))
    for t in new_tags:
        print(f"      🆕 new tag: {t}")
