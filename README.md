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
      store/           pgvector access, embeddings, dedupe
      report/          final categorised report writer
    db/schema.sql      Postgres + pgvector schema
    data/seed_urls/    hand-picked URLs for extraction experiments
    docs/decisions.md  design decisions log

## Status: in progress

- [x] Project scaffold, draft schema, decisions log
- [ ] Extraction spike: ~10 Zemoso URLs → categorised questions (OpenAI)
- [ ] Embeddings + dedupe into pgvector
- [ ] Search providers (Tavily, swappable to Serper/Brave)
- [ ] LangGraph pipeline + CLI report
- [ ] FastAPI backend + React UI

See docs/decisions.md for decided and open questions.
