// The quick live pass: a few seconds from a company name to its first questions.
//
// One web search (Tavily, with each page's text), limited to sites where candidates
// write up their own interviews. Then one streamed OpenAI call per page, all in
// parallel, each writing one JSON object per line, so questions reach the browser as
// soon as any page's model has written one. (One call over all pages took ~12s to the
// first question: the model reads every page before writing anything.) No per-page firsthand check, deduplication or tagging: that is
// the full collector's job (GitHub Actions), which runs afterwards and replaces this.

// Mirrors roles.CATEGORIES in the Python collector.
export const CATEGORIES = [
  "DSA", "LLD", "HLD", "Backend", "Database", "Messaging & Streaming", "DevOps & Cloud", "Frontend", "Data",
  "ML/AI", "Product Sense", "Metrics & Experimentation", "Estimation", "Strategy", "Execution",
  "Portfolio & Critique", "Design Exercise", "Sales Pitch & Role-play", "Pipeline & Negotiation",
  "Market & Product Knowledge", "Marketing Strategy", "Campaigns & Growth", "Operations & Process",
  "HR & Recruiting", "People Management", "Behavioral", "Other",
];

// Same exclusions as sources/search.py: pages that are never candidate write-ups, and
// people-data sites, which list individuals' contact details we must never collect.
const SKIP_URL_PARTS = ["/jobs", "/job-listings", "/careers", "youtube.com", "instagram.com", "facebook.com",
                        "/salaries", "/reviews/", "discuss.boardinfinity.com"];
const BLOCKED_SITES = ["rocketreach.co", "leadiq.com", "zoominfo.com", "apollo.io", "signalhire.com",
                       "contactout.com", "crunchbase.com", "mapquest.com", "tavily.com/knowledge", "tracxn.com"];

// Where candidates post their own interview reports. Searching everywhere mostly found
// "top 50 interview questions" articles, whose generic questions nobody was asked.
export const WRITEUP_SITES = ["geeksforgeeks.org", "medium.com", "reddit.com", "linkedin.com", "glassdoor.co.in",
                              "glassdoor.com", "ambitionbox.com", "dev.to", "hashnode.dev", "naukri.com"];

const MAX_PAGES = 6;
const PAGE_CHARS = 6000; // per page: enough for a write-up's question list, short enough to answer fast
const MAX_QUESTIONS = 40;

export type QuickSource = { url: string; title: string; site: string };
export type QuickQuestion = { text: string; category: string; source: number }; // source: index into sources
export type QuickResult = { company: string; at: number; sources: QuickSource[]; questions: QuickQuestion[] };
type Page = QuickSource & { text: string };

const siteOf = (url: string) => new URL(url).hostname.replace(/^www\./, "");

export function usablePage(url: string, text: string, company: string): boolean {
  const u = url.toLowerCase();
  if ([...SKIP_URL_PARTS, ...BLOCKED_SITES].some((p) => u.includes(p))) return false;
  if (u.includes("linkedin.com") && !u.includes("/posts/")) return false; // candidates' own posts only
  if (siteOf(u).startsWith(`${company.replace(/ /g, "")}.`)) return false; // the company's own site
  return text.toLowerCase().includes(company);
}

export async function searchPages(company: string, key: string): Promise<Page[]> {
  const res = await fetch("https://api.tavily.com/search", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({ query: `${company} interview experience`, max_results: 10, include_raw_content: true,
                           include_domains: WRITEUP_SITES }),
  });
  if (!res.ok) throw new Error(`search failed: ${res.status}`);
  const { results } = (await res.json()) as { results: { url: string; title: string; content: string; raw_content?: string }[] };
  return results
    .map((r) => ({ url: r.url, title: r.title, site: siteOf(r.url), text: (r.raw_content || r.content || "").slice(0, PAGE_CHARS) }))
    .filter((p) => usablePage(p.url, p.text, company))
    .slice(0, MAX_PAGES);
}

export function prompt(company: string, page: Page) {
  const system = `You list interview questions that candidates report being asked at ${company}, using only the page given.

Rules:
- Only questions a candidate says they were asked in a ${company} interview. If the page is a list of sample or "commonly asked" questions rather than someone's own interview, output nothing. Skip prep advice, salary talk and ads.
- Each item is a question or task as it was put to the candidate: a coding problem, a design task, a concept question, or a concrete behavioral prompt. Never describe a round ("the first round was an SQL test"), and skip vague mentions like "asked DSA questions" or "one DP problem".
- Categories: DSA is coding/algorithm problems only. Language, framework and web concepts (JavaScript hoisting, React hooks, Java streams) are Frontend or Backend; SQL and schema questions are Database; system design is HLD; class/object design is LLD.
- Rewrite each as one clear, self-contained sentence. Never include anyone's name.
- Never invent questions. If the pages report none, output nothing.
- At most 15 questions, in the order the page reports them. No duplicates.

Output one JSON object per line and nothing else (no array, no code fences):
{"q": "<question>", "category": "<one of: ${CATEGORIES.join(", ")}>"}`;
  return { system, user: `${page.title} (${page.url})\n\n${page.text}` };
}

// Lines the model still writes despite the rules: a round described, or only the kind of
// problem named ("solve a problem involving arrays"). Nobody can prepare from those.
const VAGUE = [
  /^(the|these|this|those)\s+(\w+\s+){0,2}(questions?|rounds?|tests?|interviews?)\b/i,
  /^(solve|asked|given)\s+(a|an|one|two|some)?\s*(\w+\s+)?(problems?|questions?)\s+(involving|based on|on|about|related to|using)\b/i,
];

export const isVague = (text: string) => VAGUE.some((r) => r.test(text));

// One line of model output -> a question from page `source`, or null if it isn't one.
export function parseLine(line: string, source: number): QuickQuestion | null {
  const s = line.trim().replace(/,$/, "");
  if (!s.startsWith("{")) return null;
  try {
    const o = JSON.parse(s) as { q?: unknown; category?: unknown };
    if (typeof o.q !== "string" || o.q.trim().length < 8 || isVague(o.q.trim())) return null;
    const category = typeof o.category === "string" && CATEGORIES.includes(o.category) ? o.category : "Other";
    return { text: o.q.trim(), category, source };
  } catch {
    return null;
  }
}

// Reads every page at once (one streamed call each) and calls onQuestion for each new
// question the moment any of them writes one.
export async function extractQuestions(company: string, pages: Page[], key: string, model: string,
                                       onQuestion: (q: QuickQuestion) => Promise<void>): Promise<void> {
  const seen = new Set<string>();
  const found = async (q: QuickQuestion | null) => {
    const k = q?.text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    if (q && k && !seen.has(k) && seen.size < MAX_QUESTIONS) {
      seen.add(k);
      await onQuestion(q);
    }
  };
  // one failed page shouldn't lose the others' questions
  const results = await Promise.allSettled(
    pages.map((page, i) => streamLines(prompt(company, page), key, model, (line) => found(parseLine(line, i)))));
  if (results.every((r) => r.status === "rejected")) throw (results[0] as PromiseRejectedResult).reason;
}

// One streamed chat completion, delivered a line of text at a time.
async function streamLines({ system, user }: { system: string; user: string }, key: string, model: string,
                           onLine: (line: string) => Promise<void>): Promise<void> {
  const res = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model, stream: true, temperature: 0, max_tokens: 1500,
                           messages: [{ role: "system", content: system }, { role: "user", content: user }] }),
  });
  if (!res.ok || !res.body) throw new Error(`model failed: ${res.status}`);

  // Two layers of buffering: SSE events ("data: {...}\n\n") can be split across network
  // chunks, and the model's text lines can be split across events.
  let events = "", text = "";
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    events += value;
    const frames = events.split("\n\n");
    events = frames.pop() ?? "";
    for (const frame of frames) {
      const data = frame.replace(/^data: /, "");
      if (data === "[DONE]") continue;
      try {
        text += (JSON.parse(data) as { choices: { delta: { content?: string } }[] }).choices[0]?.delta.content ?? "";
      } catch {
        continue;
      }
      const lines = text.split("\n");
      text = lines.pop() ?? "";
      for (const line of lines) await onLine(line);
    }
  }
  await onLine(text);
}
