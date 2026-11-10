from prepradar.graph import nodes


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
    state = {"company": "zemoso", "track": "Backend", "gaps": ["HLD", "LLD"], "retries": 1,
             "searched": ["zemoso system design interview round"]}
    out = nodes.plan_queries(state)
    assert out["queries"] == ["zemoso low level design OOP interview"]
    assert out["retries"] == 2
