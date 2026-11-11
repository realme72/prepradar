from prepradar.extract.extractor import chunks, ground
from prepradar.models import ExperienceDraft


def test_short_page_is_one_chunk():
    assert chunks("a" * 500, size=1000) == ["a" * 500]


def test_long_page_chunks_overlap_and_cover_the_end():
    text = "\n".join(f"line {i:04d}" for i in range(3000))  # ~30k chars
    parts = chunks(text, size=10_000, overlap=500, max_chunks=10)
    assert len(parts) >= 3
    assert parts[-1].endswith("line 2999")
    for a, b in zip(parts, parts[1:]):
        assert a[-100:] in b  # the next window re-reads the end of this one


def test_chunks_are_capped():
    assert len(chunks("x\n" * 100_000, size=10_000, max_chunks=4)) == 4


def experience(**kw):
    base = dict(summary="s", role=None, function="Engineering", position="Unknown", track="Backend",
                interview_year=None, rounds=[], outcome="Offer", difficulty_quote=None, difficulty="Hard",
                duration="null", tips=[])
    return ExperienceDraft(**{**base, **kw})


def test_experience_level_comes_from_the_title():
    assert experience(role="SDE-II", position="SDE 3 / Senior").position == "SDE 2"
    assert experience(role="Software Engineer", position="SDE 2").position == "Unknown"


def test_experience_off_ladder_and_null_strings():
    e = experience(function="Sales", position="SDE 2")
    assert (e.position, e.track, e.duration) == ("Unknown", "General", None)


def test_difficulty_and_tips_need_a_quote_from_the_page():
    page = "Overall the interview was very tough. My advice: revise\nJava streams before round 2."
    e = ground(experience(difficulty_quote="the interview was VERY tough!", tips=[
        {"quote": "My advice: revise Java streams", "advice": "Revise Java streams."},
        {"quote": "Practice system design daily", "advice": "Practice system design."},  # not on the page
    ]), page)
    assert e.difficulty == "Hard"
    assert [t.advice for t in e.tips] == ["Revise Java streams."]


def test_unquoted_difficulty_becomes_unknown():
    e = ground(experience(difficulty="Medium", difficulty_quote=None), "Two rounds, both coding.")
    assert e.difficulty == "Unknown"
