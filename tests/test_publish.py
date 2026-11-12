from prepradar.publish import guide_outline, open_question_ids, question_outline, story_outline

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


def test_a_locked_question_carries_no_text_sources_or_embedding():
    o = question_outline(q(9))
    assert "secret" not in str(o) and "https://x" not in str(o) and "e" not in o
    assert o["locked"] is True and o["category"] == "DSA"


def test_signed_out_visitors_get_the_two_most_reported_questions_only():
    qs = [q(1), q(2, reported=3), q(3, cat="HLD", reported=2), q(4, cat="HLD"), q(5, specific=False, reported=9)]
    assert open_question_ids(qs) == {2, 3}  # across categories; vague reports never count


def test_a_public_guide_says_only_that_it_exists():
    g = guide_outline({"function": "Engineering", "position": "", "track": "Backend", "since": None, "markdown": GUIDE})
    assert g["markdown"] == "" and g["locked"] is True and g["track"] == "Backend"
