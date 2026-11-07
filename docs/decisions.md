# Decisions

## Decided
- Store **questions, not chunks**: extraction at ingest, one row per question + metadata.
- Hybrid retrieval: metadata filters (company/year/category) + vector similarity.
- Every question must carry a source URL; no LLM-invented questions.
- Postgres + pgvector (already installed locally), local embeddings (bge-small, 384d).
- Python 3.12 (3.14 is too new for torch wheels).
- Interface: CLI first; web UI later in React (FastAPI backend).
- Extraction LLM: OpenAI (OPENAI_API_KEY), structured output.
- Search: Tavily first, behind a provider interface so Serper/Brave can swap in
  via SEARCH_PROVIDER when quota runs out.
- First milestone: extraction spike on ~10 hand-picked Zemoso URLs.

## Open
1. LangChain: skip and use SDKs directly, or use selected utilities?
2. User-submitted experiences in v1 or later?
3. Target scope: Indian product/startup companies only, or general?

## Revisit before public deployment
- Glassdoor/AmbitionBox are auto-fetched during the spike (low volume, personal use). Their ToS forbid scraping: switch to paste-an-experience before any public launch.
- Naukri Code360 (JS bot check) and Dataford sub-pages (429) are blocked; handle later.
