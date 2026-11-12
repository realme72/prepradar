from types import SimpleNamespace

from prepradar import pipeline
from prepradar.pipeline import Candidate, Read


def test_pages_are_read_in_waves_and_never_past_the_limit(monkeypatch):
    monkeypatch.setattr(pipeline.config, "INGEST_WORKERS", 3)
    monkeypatch.setattr(pipeline.db, "seen_urls", lambda conn: {"u0": "extracted"})
    monkeypatch.setattr(pipeline.db, "vocabulary", lambda conn: {})
    read = []
    monkeypatch.setattr(pipeline, "read_page", lambda c, company, vocab: read.append(c.url) or Read(None))

    def save(conn, company, c, r, stats):  # odd pages are rejected, which don't count
        if int(c.url[1:]) % 2:
            stats.rejected += 1
        else:
            stats.pages += 1
    monkeypatch.setattr(pipeline, "save", save)

    cands = [Candidate(f"u{i}") for i in range(10)] + [Candidate("u2")]
    stats = pipeline.ingest(None, "acme", cands, limit=3)
    assert stats.pages == 3
    # u0 cached, u2 listed twice; waves of 3, then 2 (the limit), then 1
    assert read == ["u1", "u2", "u3", "u4", "u5", "u6"]


def test_tag_judgements_are_made_up_front_and_reused(monkeypatch):
    asked = []
    monkeypatch.setattr(pipeline.db, "judge_input",
                        lambda conn, tag, cat: None if tag == "Graphs" else ["Caching", "Queues"])
    monkeypatch.setattr(pipeline, "match_tag", lambda tag, cands: asked.append((tag, cands)) or "Caching")
    qs = [SimpleNamespace(topics=["Redis Cache", "Graphs"], category="HLD"),
          SimpleNamespace(topics=["Redis Cache"], category="HLD")]
    judge = pipeline.prejudge_tags(None, qs)
    assert asked == [("Redis Cache", ["Caching", "Queues"])]  # once, despite two questions
    assert judge("Redis Cache", ["Caching", "Queues"]) == "Caching" and len(asked) == 1
    judge("Redis Cache", ["Caching", "Queues", "Redis"])  # candidates changed since: asked again
    assert len(asked) == 2
