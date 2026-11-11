"""Ingest candidate pages: fetch -> same-post check -> extract -> store -> tag -> experiences.

Shared by `prepradar ingest` and the graph's ingest node.
"""
from dataclasses import dataclass, field

from prepradar.extract.extractor import extract, extract_experiences, match_tag, same_question
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


def store_questions(conn, qs, source_id: int) -> tuple[int, list[str], dict[str, str]]:
    """Embed, dedupe and tag extracted questions. Returns (duplicates, new tags, tags
    mapped onto existing ones)."""
    vecs = embed([q.text for q in qs]) if qs else []
    dups, new_tags, mapped = 0, [], {}
    for q, vec in zip(qs, vecs):
        qid, dup = db.add_question(conn, q, source_id, vec, same_question)
        dups += dup
        for tag in q.topics:
            resolved = db.resolve_topic(conn, tag, q.category, match_tag)
            if resolved is None:
                continue
            tid, name, created = resolved
            db.tag_question(conn, qid, tid)
            if created:
                new_tags.append(f"{name} ({q.category})")
            elif name != tag:
                mapped[tag] = name
    return dups, new_tags, mapped


def ingest(conn, company: str, candidates: list[Candidate], limit: int) -> IngestStats:
    stats = IngestStats()
    seen = db.seen_urls(conn)
    for c in candidates:
        if c.url in seen:
            print(f"  cached ({seen[c.url]})  {c.url}")
            continue
        # Only accepted pages count: rejecting one is a small classifier call, and
        # counting rejects let a batch of prep guides use up the whole budget.
        if stats.pages >= limit:
            print(f"  limit of {limit} new write-ups reached; run again for the rest")
            break
        page = load_page(c.url, c.title, c.raw_text)
        if page is None and paste_only(c.url):
            print(f"  can't be read automatically; to add it, copy the post and run "
                  f"`pbpaste | uv run prepradar paste {company} '{c.url}'`")
            continue
        if page is None:
            print(f"  blocked/empty, will retry next run  {c.url}")
            continue
        posted_year = int(page.published[:4]) if page.published else None
        same = db.find_same_post(conn, company, page.text, page.title)
        if same:
            db.add_source(conn, c.url, company, "duplicate", page.site, page.title, posted_year, page.text)
            conn.commit()
            print(f"  same post as {same}, skipped  {c.url}")
            continue
        firsthand, qs = extract(page, company, db.vocabulary(conn))
        status = "extracted" if firsthand else "not_firsthand"
        source_id = db.add_source(conn, c.url, company, status, page.site, page.title, posted_year, page.text)
        if not firsthand:
            stats.rejected += 1
            conn.commit()
            print(f"  skipped: not a firsthand candidate experience  {c.url}")
            continue
        stats.pages += 1

        dups, new_tags, mapped = store_questions(conn, qs, source_id)
        exps = extract_experiences(page, company)
        db.add_experiences(conn, source_id, company, posted_year, exps)
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
    return stats
