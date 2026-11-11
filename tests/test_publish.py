from prepradar.publish import free_question_ids, guide_preview, question_outline, story_outline

GUIDE = """# Amazon interview prep

## At a glance
- 90 questions

## Process
OA then loops.

## DSA
- [Q1] Rotten Oranges

## HLD
- [Q2] Design an auction platform

## Prep checklist
1. Practise graphs [Q1]

## Cited questions
- **[Q1]** Rotten Oranges

## Sources
- [S1] https://example.com
"""


def test_guide_preview_keeps_the_first_sections_and_the_citations():
    p = guide_preview(GUIDE)
    assert "## DSA" in p and "Rotten Oranges" in p
    assert "Design an auction platform" not in p and "Practise graphs" not in p
    assert "🔒 2 more sections for subscribers" in p and "HLD, Prep checklist" in p
    assert "## Cited questions" in p and "## Sources" in p


def test_a_locked_story_carries_no_content():
    story = {"id": 1, "function": "Engineering", "position": "SDE 2", "track": "Backend", "interview_year": 2025,
             "posted_year": None, "outcome": "Offer", "difficulty": "Hard", "summary": "secret",
             "rounds": [{"name": "OA", "kind": "OA", "summary": "secret"}], "tips": ["secret"],
             "url": "https://x", "site": "x", "role": "SDE-II", "duration": "3 weeks"}
    t = story_outline(story)
    assert "secret" not in str(t) and "https://x" not in str(t)
    assert t["rounds_count"] == 1 and t["locked"] is True


def q(id, cat="DSA", reported=1, specific=True, fn="Engineering"):
    return {"id": id, "specific": specific, "category": cat, "function": fn, "times_reported": reported,
            "interview_year": 2025, "posted_year": None, "round": "Technical", "position": "SDE 2",
            "track": "Backend", "topics": ["Graphs"], "text": f"secret question {id}", "urls": ["https://x"],
            "e": "AAAA"}


def test_half_of_each_category_is_free_most_reported_first():
    qs = [q(1), q(2, reported=3), q(3), q(4, cat="HLD"), q(5, cat="HLD"), q(6, cat="HLD"), q(7, specific=False)]
    free = free_question_ids(qs)
    assert 2 in free                      # the most reported DSA question
    assert len(free & {1, 2, 3}) == 2     # ceil(3 / 2)
    assert len(free & {4, 5, 6}) == 2
    assert 7 in free                      # vague reports are free


def test_a_locked_question_carries_no_text_sources_or_embedding():
    o = question_outline(q(9))
    assert "secret" not in str(o) and "https://x" not in str(o) and "e" not in o
    assert o["locked"] is True and o["category"] == "DSA"
