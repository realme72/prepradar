# PrepRadar

> 🚧 **Work in progress** — scaffold done; extraction spike underway. Not usable yet.

Company-specific interview intelligence. Ask "Zemoso, backend, 2026" and get the
questions actually reported, deduped, categorised (DSA / LLD / HLD / Backend /
Frontend / Behavioral), filtered by year and round, every one linked to its source.

## Pipeline (LangGraph)

    check_cache ─hit─────────────────────────────┐
        │ miss                                   ▼
    search ─► fetch ─► extract ─► embed+dedupe ─► retrieve ─► report
        ▲                                            │
        └──────── coverage_check (max 2 retries) ◄───┘

## Layout

    src/prepradar/
      models.py        Pydantic schemas (Question, Category, Round...)
      config.py        env/settings
      cli.py           entry point
      graph/           LangGraph state, nodes, graph wiring
      sources/         web search (Tavily) + page fetch/clean
      extract/         LLM extraction prompts + structured output
      store/           pgvector access (insert-time dedupe, tag resolution, hybrid search), embeddings
      report/          final categorised report writer
    db/schema.sql      Postgres + pgvector schema
    data/seed_urls/    hand-picked URLs for extraction experiments
    docs/decisions.md  design decisions log

## Usage (local)

    createdb prepradar && uv run prepradar init
    uv run prepradar search zemoso          # dry run: candidate pages
    uv run prepradar ingest zemoso --limit 15
    uv run prepradar run zemoso --track Backend   # LangGraph: cache → search → ingest → coverage loop → report
    uv run prepradar guide zemoso --track Backend # prep guide from stored data -> reports/
    uv run prepradar report zemoso --track Backend --since 2023
    uv run prepradar ask zemoso "caching and performance"
    uv run prepradar topics --discovered

## Status: in progress

- [x] Project scaffold, draft schema, decisions log
- [x] Extraction spike: Zemoso URLs → categorised questions (OpenAI)
- [x] pgvector storage: insert-time dedupe, auto-discovered tags, semantic `ask`
- [x] Search providers (Tavily, falls through to Serper/Brave on quota)
- [x] LangGraph pipeline: cache check, coverage-gap retry loop (`prepradar run`)
- [x] Grounded prep guide: facts computed in code, every claim cites Q#/S#, invalid citations removed
- [ ] FastAPI backend + React UI

See docs/decisions.md for decided and open questions.
