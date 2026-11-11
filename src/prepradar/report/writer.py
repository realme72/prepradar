"""The G of RAG: a prep guide written ONLY from retrieved questions.

1. Number retrieved questions Q1..Qn and their pages S1..Sn.
2. Compute the facts (counts, top topics, rounds, years) in code; LLMs miscount.
3. The LLM writes the guide, citing Q/S ids for every claim (structured output).
4. We drop any cited id that doesn't exist and report how many were dropped.
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from pydantic import BaseModel, Field

from prepradar import config
from prepradar.extract.extractor import parse
from prepradar.models import Category
from prepradar.roles import Scope

CATEGORY_ORDER = list(Category.__args__)
MAX_PER_CATEGORY = 25  # keeps the prompt bounded for companies with lots of data


class Section(BaseModel):
    category: Category  # exact category names, so sections sort and match
    summary: str = Field(description="2-4 sentences on what this company asks in this area, citing [Q#]/[S#]")
    must_prepare: list[str] = Field(description="Q ids of the questions most worth practising, most important first")


class ChecklistItem(BaseModel):
    item: str = Field(description="A concrete prep action, e.g. 'Practise in-place array problems'")
    question_ids: list[str] = Field(description="Q ids that justify this item")


class PrepGuide(BaseModel):
    process_overview: str = Field(description="What the interview process looks like, citing [S#]/[Q#]")
    sections: list[Section]
    checklist: list[ChecklistItem] = Field(description="5-10 items, highest-frequency topics first")
    caveats: list[str] = Field(description="Data limitations a reader must know: thin areas, old data, few sources")


SYSTEM = """You write interview prep guides for {company} ({scope}) using ONLY the data given.

Hard rules:
- Every claim must be supported by the questions (Q#) or sources (S#) provided. Cite them
  inline like [Q3] or [S2]. If the data doesn't show something, don't say it.
- Do not add general interview advice, typical industry practice, or questions that
  aren't in the data. "Zemoso probably also asks X" is forbidden.
- Use the precomputed FACTS for any number. Never count yourself.
- Write exactly one section for each category in REQUIRED SECTIONS, no more, no fewer.
  Skip vague questions in must_prepare; they can inform a summary ("candidates mention
  medium DSA problems [Q9]").
- Caveats: name the thin core categories from FACTS, say how old the data is, and how
  many write-ups it rests on. No generic caveats.
"""


class MissingSections(BaseModel):
    sections: list[Section]


@dataclass
class Grounded:
    guide: PrepGuide
    questions: dict[str, dict]  # Q id -> question row
    sources: dict[str, str]     # S id -> url
    facts: str
    dropped_citations: int
    url_to_sid: dict[str, str]


def _select(questions: list[dict]) -> list[dict]:
    by_cat = defaultdict(list)
    for q in questions:
        by_cat[q["category"]].append(q)
    picked = []
    for cat in CATEGORY_ORDER:
        rows = sorted(by_cat.get(cat, []),
                      key=lambda q: (-q["times_reported"], -(q["interview_year"] or q["posted_year"] or 0)))
        picked += rows[:MAX_PER_CATEGORY]
    return picked


def _facts(questions: list[dict], n_sources: int, scope: Scope) -> str:
    from prepradar.graph.nodes import MIN_PER_CATEGORY

    specific = [q for q in questions if q["specific"]]
    cats = Counter(q["category"] for q in specific)
    topics = Counter(t for q in specific for t in (q["topics"] or []))
    years = sorted({y for q in questions if (y := q["interview_year"] or q["posted_year"])})
    repeated = [q for q in specific if q["times_reported"] > 1]
    return "\n".join([
        f"- {len(questions)} questions ({len(specific)} specific) from {n_sources} candidate write-ups",
        f"- Per category: " + ", ".join(f"{c} {n}" for c, n in cats.most_common()),
        f"- Most frequent topics: " + ", ".join(f"{t} {n}" for t, n in topics.most_common(12)),

        f"- Years covered: {years[0]}–{years[-1]}" if years else "- Years covered: unknown",
        f"- Positions: " + ", ".join(f"{p} {n}" for p, n in Counter(q["position"] for q in questions).most_common()),
        f"- Reported by more than one candidate: {len(repeated)} questions",
        f"- Thin core categories (fewer than {MIN_PER_CATEGORY} questions): "
        + (", ".join(c for c in scope.core() if cats.get(c, 0) < MIN_PER_CATEGORY) or "none"),
    ])


def _rounds_per_source(questions: list[dict], url_to_sid: dict[str, str]) -> str:
    """Which round types each write-up describes. Process claims need this per
    candidate; a total across candidates reads as '46 technical rounds'."""
    order = ["OA", "Technical", "Managerial", "HR"]
    seen: dict[str, set[str]] = defaultdict(set)
    for q in questions:
        for url in q["urls"] or []:
            if q["round"] != "Unknown":
                seen[url_to_sid[url]].add(q["round"])
    rows = [f"  - {sid}: {', '.join(r for r in order if r in rounds)}"
            for sid, rounds in sorted(seen.items(), key=lambda kv: int(kv[0][1:]))]
    return "- Round types each write-up describes (one candidate each):\n" + ("\n".join(rows) or "  - none stated")


def write_guide(scope: Scope, questions: list[dict]) -> Grounded:
    picked = _select(questions)
    sources: dict[str, str] = {}
    url_to_sid: dict[str, str] = {}
    qmap: dict[str, dict] = {}
    lines = []
    for i, q in enumerate(picked, 1):
        sids = []
        for url in q["urls"] or []:
            if url not in url_to_sid:
                url_to_sid[url] = f"S{len(url_to_sid) + 1}"
                sources[url_to_sid[url]] = url
            sids.append(url_to_sid[url])
        qid = f"Q{i}"
        qmap[qid] = q
        year = q["interview_year"] or q["posted_year"] or "?"
        lines.append(
            f"{qid} [{q['category']}; {', '.join(q['topics'] or []) or '-'}; round {q['round']}; {year}; "
            f"×{q['times_reported']}{'; VAGUE' if not q['specific'] else ''}] {q['text']}  (sources: {', '.join(sids)})"
        )
    # Facts describe every stored question; only the list sent to the model is capped
    # per category. Counting the capped list made a pack's guide disagree with its cover.
    all_urls = {u for q in questions for u in q["urls"] or []}
    facts = _facts(questions, len(all_urls), scope) + "\n" + _rounds_per_source(picked, url_to_sid)
    source_lines = [f"{sid}: {url}" for sid, url in sources.items()]

    # Which sections the guide must have is decided here, not left to the model:
    # with ~100 questions it sometimes wrote one section and stopped.
    required = [c for c in CATEGORY_ORDER if any(q["category"] == c and q["specific"] for q in picked)]
    instructions = SYSTEM.format(company=scope.company.title(), scope=scope.label())
    data = ("FACTS\n" + facts + "\n\nSOURCES\n" + "\n".join(source_lines)
            + "\n\nQUESTIONS\n" + "\n".join(lines))

    guide: PrepGuide = parse(
        "guide",
        model=config.OPENAI_MODEL,
        instructions=instructions,
        input=f"REQUIRED SECTIONS: {', '.join(required)}\n\n{data}",
        text_format=PrepGuide,
        temperature=0.2,
    ).output_parsed
    guide.sections = [s for s in guide.sections if s.category in required]
    missing = [c for c in required if c not in {s.category for s in guide.sections}]
    if missing:  # one follow-up call for just the sections it skipped
        extra: MissingSections = parse(
            "guide",
            model=config.OPENAI_MODEL,
            instructions=instructions,
            input=f"REQUIRED SECTIONS: {', '.join(missing)}\n\n{data}",
            text_format=MissingSections,
            temperature=0.2,
        ).output_parsed
        guide.sections += [s for s in extra.sections if s.category in missing]
    seen: set[str] = set()  # one section per category, even if the model repeated one
    guide.sections = [s for s in guide.sections if not (s.category in seen or seen.add(s.category))]
    dropped = _enforce_citations(guide, set(qmap), set(sources))
    for sec in guide.sections:  # the prompt says so, but don't rely on it
        sec.must_prepare = [q for q in sec.must_prepare if qmap[q]["specific"]]
    return Grounded(guide, qmap, sources, facts, dropped, url_to_sid)


def _enforce_citations(guide: PrepGuide, qids: set[str], sids: set[str]) -> int:
    """Remove references to ids we never gave the model. Returns how many were removed."""
    dropped = 0
    for s in guide.sections:
        keep = [q for q in s.must_prepare if q in qids]
        dropped += len(s.must_prepare) - len(keep)
        s.must_prepare = keep
    for c in guide.checklist:
        keep = [q for q in c.question_ids if q in qids]
        dropped += len(c.question_ids) - len(keep)
        c.question_ids = keep
    # inline [Q#]/[S#] in prose: count unknown ones (left visible, flagged by render)
    prose = " ".join([guide.process_overview, *(s.summary for s in guide.sections)])
    for kind, num in re.findall(r"\[(Q|S)(\d+)\]", prose):
        if f"{kind}{num}" not in (qids if kind == "Q" else sids):
            dropped += 1
    return dropped


def _cited_ids(g: Grounded) -> list[str]:
    prose = " ".join([g.guide.process_overview, *(s.summary for s in g.guide.sections)])
    ids = re.findall(r"\[(Q\d+)\]", prose)
    ids += [q for s in g.guide.sections for q in s.must_prepare]
    ids += [q for c in g.guide.checklist for q in c.question_ids]
    seen = dict.fromkeys(i for i in ids if i in g.questions)
    return sorted(seen, key=lambda i: int(i[1:]))


def render_markdown(scope: Scope, g: Grounded) -> str:
    title = f"# {scope.company.title()} interview prep — {scope.label()}"
    out = [title, "", "_Generated only from candidate-reported questions. "
           "Every [Q#]/[S#] links back to a real write-up._", "", "## At a glance", g.facts, "",
           "## Process", g.guide.process_overview, ""]
    for s in sorted(g.guide.sections, key=lambda s: CATEGORY_ORDER.index(s.category)
                    if s.category in CATEGORY_ORDER else 99):
        out += [f"## {s.category}", s.summary, ""]
        for qid in s.must_prepare:
            q = g.questions[qid]
            seen = f" ×{q['times_reported']}" if q["times_reported"] > 1 else ""
            out.append(f"- **[{qid}]** {q['text']}{seen}")
        out.append("")
    out += ["## Prep checklist"]
    out += [f"{i}. {c.item} " + " ".join(f"[{q}]" for q in c.question_ids) for i, c in enumerate(g.guide.checklist, 1)]
    out += ["", "## Caveats"] + [f"- {c}" for c in g.guide.caveats]
    cited = _cited_ids(g)
    if cited:
        out += ["", "## Cited questions"]
        for qid in cited:
            q = g.questions[qid]
            sids = " ".join(f"[{g.url_to_sid[u]}]" for u in q["urls"] or [])
            out.append(f"- **[{qid}]** {q['text']} — {q['category']} · {sids}")
    out += ["", "## Sources"] + [f"- [{sid}] {url}" for sid, url in g.sources.items()]
    if g.dropped_citations:
        out += ["", f"_Grounding check: removed or flagged {g.dropped_citations} citation(s) to ids not in the data._"]
    return "\n".join(out) + "\n"
