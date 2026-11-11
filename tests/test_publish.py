from prepradar.publish import _teaser, guide_preview, pack_id

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
    assert "🔒 2 more sections with the pack" in p and "HLD, Prep checklist" in p
    assert "## Cited questions" in p and "## Sources" in p


def test_a_locked_story_carries_no_content():
    story = {"id": 1, "function": "Engineering", "position": "SDE 2", "track": "Backend", "interview_year": 2025,
             "posted_year": None, "outcome": "Offer", "difficulty": "Hard", "summary": "secret",
             "rounds": [{"name": "OA", "kind": "OA", "summary": "secret"}], "tips": ["secret"],
             "url": "https://x", "site": "x", "role": "SDE-II", "duration": "3 weeks"}
    t = _teaser(story, "amazon-engineering")
    assert "secret" not in str(t) and "https://x" not in str(t)
    assert t["rounds_count"] == 1 and t["locked"] == "amazon-engineering"


def test_pack_ids_are_url_safe():
    assert pack_id("jp morgan", "People / HR") == "jp-morgan-people-hr"
