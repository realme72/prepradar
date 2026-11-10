from prepradar.store.db import resolve_topic


def test_tags_restating_a_category_are_dropped():
    # returns before touching the database, so no connection is needed
    for tag in ("System Design", "DSA", "backend", "Algorithms"):
        assert resolve_topic(None, tag, "HLD", judge=None) is None
