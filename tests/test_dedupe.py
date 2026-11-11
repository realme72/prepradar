from prepradar.store.db import pick_duplicate


def rows(*sims, specific=True):
    return [{"id": i + 1, "text": f"q{i + 1}", "specific": specific, "sim": s} for i, s in enumerate(sims)]


def judge_never_called(new, existing):
    raise AssertionError("judge should not be called")


def test_near_identical_is_a_duplicate_without_asking():
    assert pick_duplicate(rows(0.93, 0.85), "new", True, judge_never_called) == 1


def test_far_apart_is_new_without_asking():
    assert pick_duplicate(rows(0.70, 0.65), "new", True, judge_never_called) is None


def test_close_pairs_go_to_the_judge_with_only_close_candidates():
    seen = {}

    def judge(new, existing):
        seen["existing"] = existing
        return 1

    assert pick_duplicate(rows(0.86, 0.82, 0.75), "new", True, judge) == 2
    assert seen["existing"] == ["q1", "q2"]  # 0.75 is below the judge band


def test_judge_saying_different_keeps_the_question():
    assert pick_duplicate(rows(0.86), "new", True, lambda new, existing: None) is None


def test_no_judge_means_only_near_identical_counts():
    assert pick_duplicate(rows(0.86), "new", True, None) is None


def test_empty_table():
    assert pick_duplicate([], "new", True, judge_never_called) is None


def test_a_vague_report_is_never_judged_the_same_as_a_specific_question():
    # "Solve a graph problem" must not become a second report of "Currency Converter"
    assert pick_duplicate(rows(0.85), "Solve a graph problem.", False, judge_never_called) is None
