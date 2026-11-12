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

## Experiences (2026-11-11)

- **Questions alone lost the story.** Each write-up's rounds in order, outcome, difficulty, duration and tips now go in an `experiences` table: one row per candidate, so a review page gives one per reviewer. It's a separate LLM call, so the question prompt is unchanged.
- **Difficulty and tips must be quoted.** On the first try the model rated almost every interview "Medium" and wrote generic tips nobody gave (a prachub page with no advice got three). The model now copies the candidate's words, and `ground()` drops any difficulty or tip whose quote isn't on the page. This is the same idea as the guide's citation check.
- **Long pages are read in chunks.** Question extraction used to stop at 15k characters; it now reads up to 4 overlapping 15k windows. The experience call reads up to 60k at once, so a story isn't split.
- **Page text is still not stored**, because it would keep people's names. `prepradar experiences` re-fetches sources to backfill, and pages that can't be re-fetched are skipped.
- **Token log.** Every OpenAI call goes through `parse()`, which writes the token counts to `llm_usage`. `prepradar usage` sums them per model and purpose. Cost in dollars is on the OpenAI dashboard.

## Exact DSA questions and subtopics (2026-11-11)

- **"Solve problems on arrays and hashmaps" was counted as a question.** The specific/vague rule allowed short concept questions, and the model stretched that to cover topic-only lines. `DSA_SPECIFIC_RULE` now asks for something a candidate can look up and practise: a named problem, a statement of what to compute, or a concrete concept question. The rule is shared by extraction and `prepradar respecify`, which re-judges stored DSA questions in both directions. A first, stricter wording also demoted named problems ("Currency Converter") and concept questions ("DFS vs BFS"), so the examples now cover those. Result: 112 specific, 39 vague.
- **Subtopics** come from the tags of the questions in the selected category, most common first. The list is sorted by how many candidates reported each question. Vague reports follow the selected category.

## Free live site and pack unlocks (2026-11-11)

- **Static site plus one Cloudflare Worker, at no cost.** The React app reads exported JSON (`prepradar export`); `static.ts` answers the same URLs FastAPI does, so the components didn't change. Search runs the same bge-small model in the browser. transformers.js loads from a pinned jsDelivr URL because its 25MB WebAssembly file is over Cloudflare's per-file limit.
- **Packs unlock content on the site; there's no PDF** (the user's call). Locked stories and full guides are left out of the public JSON entirely. Only the Worker serves them, from KV, to holders of an HMAC-signed token issued after it verifies the payment with Razorpay. Tokens need no database.
- **Prices live in `packs/catalog.json`**, bundled into the Worker, never sent by the browser. **Recovery uses the Razorpay payment ID**, which only the buyer gets, so access works on a new device without accounts or email.
- A function with no pack keeps all of its content free.

## LeetCode Discuss (2026-11-11)

- **Zero LeetCode pages had ever been stored**, despite a "leetcode discuss" search. LeetCode answers automated requests with 403 (a Cloudflare bot check), and Tavily returns no text for its posts either, so each one was dropped as "empty". We don't try to get past a site's bot protection. LeetCode is now paste-only: searches still list its posts, and a person copies a post's text into `prepradar paste COMPANY URL`. The text goes through the same pipeline, with the URL as the source.

## Subscription with Google sign-in, replacing per-pack unlocks (2026-11-11)

- **The user's model: ₹49/month unlocks the whole site, with real accounts.** Free visitors see half of each category's questions (most reported first), 3 stories per function and guide previews. The rest shows as blurred cards behind a paywall.
- **The blur hides nothing readable.** Locked questions are in the public JSON only as outlines (category, topics, how often reported), with no text, links or embedding. The cards show placeholder words. Subscribers get the real text from `/api/content`, served from KV.
- **Google sign-in, verified by the Worker:** the RS256 signature is checked against Google's JWKS, along with audience, issuer and expiry. The Worker then issues its own HMAC session. The only thing stored per user is Google's numeric id plus the subscription's id, status and period end. Name and email are shown in the browser and never saved.
- **Razorpay Subscriptions + webhooks.** Checkout is verified with HMAC(payment_id|subscription_id). Webhooks, signed over the raw body, keep renewals, halts and cancellations current. If a renewal webhook is missed, the record is refreshed from Razorpay once its paid period is over. Cancelling stops at the end of the cycle, and access lasts until then.
- **Bug caught in the browser:** routing `/api/me` to the Worker by string prefix also caught `/api/meta`, which emptied the filters. Routes are now matched by whole path segments.

## Visitors request companies (GitHub Actions + Neon)

A visitor looking for a company that isn't listed had no way forward. The site now has a company search box, and any name not on the site gets a "Get questions for X" option.

- **Where the collector runs.** The collector (Python, PyTorch, LangGraph) can't run in a Worker. GitHub Actions runs it for free on a public repo, and the Worker starts it with `workflow_dispatch`. A free always-on server would need a card or sleep anyway.
- **Database.** Actions needs a database it can reach, so the data moves to Neon's free Postgres (pgvector included).
- **Guides.** They were `reports/*.md` files, which a fresh Actions checkout doesn't have. They moved to a `guides` table; `prepradar import-guides` loaded the old files.
- **Cost guard.** Each collection costs OpenAI and search credit, so requests need Google sign-in and are capped: 2 per user per day (5 for subscribers) and 20 for the whole site. A name found empty is blocked for a week.
- **Concurrency.** Different companies collect side by side, but publishing is one at a time. GitHub keeps only the newest waiting publish run, which still includes everything, because each export reads the whole database.
- **KV write budget.** The free plan allows 1,000 writes a day. The upload sends only companies whose locked content changed, tracked by a hash manifest in KV.
- **CI install size.** On Linux, PyTorch comes from its CPU-only index. The default build pulls several GB of CUDA libraries the embedding model never uses.

## Answers in seconds: quick live pass + nightly pre-collection

A full collection takes 3–10 minutes, and people searching a company won't wait that long.

- **Quick live pass in the Worker.** It runs one Tavily search, limited to write-up sites (GeeksforGeeks, Medium, Reddit, LinkedIn posts, Glassdoor, AmbitionBox…). An open web search mostly returned "top 50 interview questions" articles.
- **One streamed call per page, in parallel.** A single call over all pages took about 12s to its first question, because the model reads everything before writing. Per-page calls take about 1s after the search, so the first question appears in about 2–5s. Output is one JSON object per line, so each question can be forwarded the moment it's complete.
- **Lower bar than the collector, and labelled as such.** There's no firsthand check per page, no tags and no deduplication beyond exact text. A regex drops lines that describe a round or only name a problem type ("solve a problem involving arrays"); the model kept writing those despite the rules. The full collection replaces the quick results 15–25 minutes later (the first real run, Swiggy, took 21 minutes for 131 questions).
- **Cost guard.** Under ₹1 per quick pass. It needs sign-in and is capped: 5 per user per day (15 for subscribers), 100 for the site. Results are cached for 14 days, so a popular company costs once.
- **Nightly pre-collection.** `companies.txt` lists about 150 companies people interview for in India. The nightly job takes the next N not yet tried, so most searches are instant within a few weeks.

## Free tier cut to 2 questions per company

Half of each category was free, which gave away most of the value. Now anyone not subscribed, signed in or not, sees each company's 2 most reported questions and 2 newest stories. Everything else, including vague reports and every prep guide, is in the subscriber file served from KV. The public file only shows that a guide exists. Signing in alone unlocks nothing; it's needed to subscribe and for quick searches.

## Posting month

- **Sources keep the full publish date** (`posted_on`), not just the year, so cards say "posted Mar 2025". A question shows its newest write-up's month; one with a stated interview year shows both ("interviewed 2024 · posted Mar 2025").
- **The date comes from the page's metadata** (trafilatura), never from the model. Pages read from the search provider's text have none and keep showing a year or nothing. `prepradar dates` re-fetched older sources to fill it in.
- **The quick pass asks the model for the month** only when the page shows it (`{"posted": "YYYY-MM"}` as its first line). Months in the future or before 2005 are dropped.
