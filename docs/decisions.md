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

## Fixed: the post-UI known gaps
- Near-duplicates: pairs between DEDUPE_JUDGE (0.80) and DEDUPE_THRESHOLD (0.88) go to an
  LLM judge; a vague report is never judged the same as a specific question. The score
  alone can't decide ("debounce function" = "what is debounce" at 0.856, but "debug a
  failing API" != "debug a slow API" at 0.863). gpt-4o-mini flip-flopped on this, so the
  judge uses JUDGE_MODEL (gpt-5.4-mini). `prepradar dedupe` cleans stored data: 8 merged
  out of 48 close pairs.
- Tag sprawl: the tag judge can now call a tag generic (dropped), and is consulted for
  every new tag. Discovered tags stay provisional (stored, not shown) until 2+ sources
  use them. `prepradar topics --review` cleaned 88 discovered tags: 10 dropped, 9
  merged, 30 shown.
- Categories: new Data category (analytics SQL, pipelines, Spark); Frontend now names JS
  language and browser topics. `prepradar recategorise` re-sorted stored questions
  (Other: 39 -> 12) and tags follow their questions' category.

## Roles beyond engineering
- Every question has a function (Engineering, Product, Data, Design, Sales, Marketing,
  Operations, People / HR) and a position on that function's ladder (SDE 1..Principal,
  APM..Director of Product, SDR..Sales Manager). Managers are rungs, not a function, so
  an engineering manager's system design and people questions stay under Engineering.
  Track (Backend, Frontend...) is an engineering specialty only. All of it lives in
  `roles.py`.
- Engineering levels are read off the title by rule (`engineering_level`): LLMs either
  invented "SDE 2" for a plain "Software Engineer" or dropped a stated "Staff". A title
  with no level stays Unknown ("Level not stated" in the UI).
- Searches are built from the scope (function, role) and include year-specific queries:
  search engines rank recent posts first, so older write-ups need asking for by year.
- `prepradar reposition` filled function/position on stored questions.

## Firsthand check, round 3
- Classification uses JUDGE_MODEL with low reasoning. gpt-4o-mini accepted guides that
  say they're "based on candidates' experiences" (interviewquery), and with no reasoning
  gpt-5.4-mini flipped on borderline pages; "low" was stable, "medium" no better.
- Glassdoor and AmbitionBox interview-review URLs count as candidate reviews by rule:
  their AI-written model answers fill the start of the page and made the classifier
  flip-flop. Extraction already ignores model answers.
- `prepradar recheck` re-runs the check on accepted sources: 13 of 73 dropped.

## Known gaps
- An AI-written forum summary (boardinfinity) still occasionally passes as reviews.
- Non-engineering data is thin until runs are made for those functions (Amazon Product:
  40 questions after the recheck).
- The tag judge merges narrower tags into broader ones (DENSE_RANK -> SQL, Cycle
  Detection -> Graphs) despite its instructions. Fine for sprawl; loses some detail.
- A few vague tags that 2+ sources used still show ("Operational Concerns", "Reflection").
- Each run reads ~12 write-ups per search round; big companies need several refresh runs.

## UI review fixes (2026-11-11)

- **Dropdown counts follow Track and Year** and count specific questions only, so "SDE 2 (26)" opens a list of 26. Track only narrows engineering rows.
- **Guides are saved per year filter** (`since-2025` in the file name). Before, a year-filtered view silently showed the all-years guide.
- **"Build guide from current questions"**: `POST /api/companies/{c}/guide` writes a guide from stored data, with no web search. The Prep guide tab offers it when no guide exists for the filters.
- **Track is disabled, not hidden, outside Engineering**, so the layout doesn't jump. The chosen track is kept in state and comes back when switching back to Engineering.
- **discuss.boardinfinity.com is rejected by URL rule**: its posts are AI summaries, and the classifier passed one on a re-run.
