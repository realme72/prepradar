from prepradar.models import QuestionDraft
import pytest

from prepradar.roles import Scope, engineering_level
from prepradar.sources.search import broad_queries


def draft(**kw):
    base = dict(text="q", specific=True, category="Behavioral", topics=[], round="Technical", role=None,
                function="Engineering", position="SDE 2", track="Backend", interview_year=None)
    return QuestionDraft(**{**base, **kw})


def test_position_must_be_on_the_functions_ladder():
    assert draft(function="Product", position="SDE 2").position == "Unknown"
    assert draft(function="Product", position="Product Manager").position == "Product Manager"


def test_tracks_only_apply_to_engineering():
    assert draft(function="Sales", position="Account Executive", track="Backend").track == "General"
    assert Scope("x", "Sales", track="Backend").track is None


def test_managers_also_prepare_people_management():
    assert "People Management" in Scope("x", position="Engineering Manager").core()
    assert "People Management" not in Scope("x", position="SDE 2").core()


def test_broad_queries_follow_the_role_and_reach_back_in_years():
    qs = broad_queries(Scope("amazon", "Sales"), this_year=2026)
    assert "amazon account executive interview experience" in qs
    assert "amazon sales interview experience 2023" in qs  # older posts only surface when asked by year


def test_guide_file_names_are_safe():
    assert Scope("amazon", "People / HR", "HR Business Partner").slug() == "amazon-people-hr-hr-business-partner"


@pytest.mark.parametrize("title, level", [
    ("SDE-I", "SDE 1"), ("Software Development Engineer I", "SDE 1"), ("SDE-1 New Grad", "SDE 1"),
    ("Associate Software Engineer", "SDE 1"), ("SDE2", "SDE 2"), ("Software Development Engineer 2", "SDE 2"),
    ("SDE-3", "SDE 3 / Senior"), ("Senior Software Engineer 1", "SDE 3 / Senior"),
    ("Lead Software Engineer", "SDE 3 / Senior"), ("Staff Backend Engineer", "Staff Engineer"),
    ("Principle Software Engineer", "Principal Engineer"), ("SDE Intern", "Intern"),
    ("Engineering Manager", "Engineering Manager"),
    # no level stated: never guess
    ("Software Engineer", "Unknown"), ("Backend Engineer", "Unknown"), ("AI Engineer", "Unknown"),
    ("Site Reliability Engineer", "Unknown"), ("SDE", "Unknown"),
])
def test_engineering_level_is_read_off_the_title(title, level):
    assert engineering_level(title) == level


def test_extraction_uses_the_title_rule_for_engineering():
    assert draft(role="Senior Software Engineer", position="Unknown").position == "SDE 3 / Senior"
    assert draft(role="Software Engineer", position="SDE 2").position == "Unknown"
