"""Wires nodes and conditional edges into the compiled graph.

    START → check_cache ─┬─(cached)──────────────────────────────┐
                         └─(search)→ plan_queries → search → ingest → coverage_check
                                         ▲                               │
                                         └──(gaps, retries left)─────────┤
                                                                         └─(done)→ report → END
"""
from langgraph.graph import END, START, StateGraph

from prepradar.graph import nodes
from prepradar.graph.state import GraphState


def build():
    g = StateGraph(GraphState)
    g.add_node("check_cache", nodes.check_cache)
    g.add_node("plan_queries", nodes.plan_queries)
    g.add_node("search", nodes.search)
    g.add_node("ingest", nodes.ingest_pages)
    g.add_node("coverage_check", nodes.coverage_check)
    g.add_node("report", nodes.report)

    g.add_edge(START, "check_cache")
    g.add_conditional_edges("check_cache", nodes.after_cache, ["plan_queries", "coverage_check"])
    g.add_edge("plan_queries", "search")
    g.add_edge("search", "ingest")
    g.add_edge("ingest", "coverage_check")
    g.add_conditional_edges("coverage_check", nodes.after_coverage, ["plan_queries", "report"])
    g.add_edge("report", END)
    return g.compile()
