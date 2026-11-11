from prepradar.graph import nodes
from prepradar.roles import Scope


def route(**state):
    return nodes.after_coverage({"gaps": [], "retries": 0, "last_new_questions": 0, **state})


def test_no_gaps_goes_to_retrieve():
    assert route(gaps=[]) == "retrieve"


def test_gaps_on_first_pass_trigger_a_targeted_search():
    assert route(gaps=["HLD"], retries=0) == "plan_queries"


def test_stops_when_retry_budget_is_spent():
    assert route(gaps=["HLD"], retries=nodes.MAX_RETRIES, last_new_questions=5) == "retrieve"


def test_stops_when_a_targeted_search_found_nothing_new():
    assert route(gaps=["HLD"], retries=1, last_new_questions=0) == "retrieve"


def test_keeps_going_while_targeted_searches_add_questions():
    assert route(gaps=["HLD"], retries=1, last_new_questions=4) == "plan_queries"


def test_gap_queries_skip_ones_already_run():
    state = {"scope": Scope("zemoso", track="Backend"), "gaps": ["HLD", "LLD"], "retries": 1,
             "searched": ["zemoso system design round interview experience"]}
    out = nodes.plan_queries(state)
    assert "zemoso system design round interview experience" not in out["queries"]
    assert "zemoso SDE 2 interview experience system design" in out["queries"]
    assert "zemoso interview experience low level design round" in out["queries"]
    assert out["retries"] == 2


def test_non_engineering_gaps_search_by_role_and_round():
    scope = Scope("amazon", "Product", "Product Manager")
    assert nodes.gap_queries(scope, "Estimation") == ["amazon Product Manager interview experience guesstimate round"]
