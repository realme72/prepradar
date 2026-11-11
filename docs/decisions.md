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

## Fixed: shallow results for big companies (Amazon: 1 LLD, 1 HLD)
- Firsthand is now its own small classifier call (`classify`, page_kind + evidence) before
  extraction. Bundled into extraction, gpt-4o-mini passed question banks (igotanoffer) and
  SEO guides (usegreenroom). `prepradar forget URL` removes a wrongly accepted source.
- Gap queries say "interview experience", never "interview questions" (that phrasing
  returns prep guides), with SDE-2/senior variants since design rounds are in
  experienced-hire loops. Broad queries include SDE-2 and senior experiences too.
- The per-round page limit counts only accepted write-ups; rejects are cheap now.
- The guide's sections are fixed in code (every category with specific questions); a
  follow-up call fills any the model skipped.
- Result: Amazon went from 75 questions (48 from one question bank, LLD 1, HLD 1) to 96
  from 21 write-ups (LLD 13, HLD 17).

## Known gaps (to do after the UI)
- Near-duplicate questions below the 0.88 threshold ("What are the SOLID principles?" vs
  "What are design patterns and SOLID principles?"): shortlist + LLM judge, as for tags.
- Tag sprawl on bigger companies (28 new tags for Razorpay): tags naming the specific design
  problem ("Wallet System") instead of a concept. Idea: provisional tags that only become
  visible once used by 2+ sources.
- Some frontend questions get odd categories/tags (CORS, Closures under Other; Type
  Coercion under DSA), seen in the Razorpay re-run.
- No Data category: data-analyst / data-engineering questions land in Other.
