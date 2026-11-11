"""LangGraph state passed between nodes.

Each node returns a partial dict; LangGraph merges it into the state. Fields
annotated with operator.add are appended to instead of replaced, so `searched`
and `log` accumulate across loop iterations.
"""
import operator
from typing import Annotated, TypedDict

from prepradar.roles import Scope


class GraphState(TypedDict, total=False):
    # input
    scope: Scope        # company, function, position, track, since
    limit: int          # max new pages sent to the LLM per search round
    refresh: bool       # search even if cached data looks sufficient
    with_guide: bool    # run the LLM guide writer at the end (default True)

    # working state
    cached: bool                                  # check_cache: enough fresh data already?
    queries: list[str]                            # plan_queries -> search
    searched: Annotated[list[str], operator.add]  # every query run in this graph run
    candidates: list                              # search -> ingest (pipeline.Candidate)
    retries: int                                  # gap-filling rounds so far
    last_new_questions: int                       # new questions added by the last ingest
    coverage: dict[str, int]                      # category -> specific question count
    gaps: list[str] | None                        # core categories below the minimum

    # output
    questions: list[dict]
    guide_md: str                                 # the grounded prep guide, as Markdown
    log: Annotated[list[str], operator.add]       # human-readable decisions, in order
