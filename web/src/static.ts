// The live site's "backend": answers the FastAPI URLs from the exported JSON in
// /data/, in the browser. Mirrors store/db.py's filters so both builds show the same
// lists. Subscribers' locked content comes from the Worker (/api/content).
import { ApiError, getJson, type Experience, type Guide, type Meta, type Question } from "./api";
import { currentSession } from "./auth";

type Row = Question & { e?: string }; // e = int8 embedding, base64 (absent on locked outlines)
type CompanyFile = {
  company: string;
  questions: Row[];
  experiences: Experience[];
  guides: (Guide & { function: string; position: string; track: string; since: number | null })[];
};
type Index = { updated: string; companies: { company: string; questions: number }[]; meta: Meta };
type Locked = Omit<CompanyFile, "company">;
type Scope = { function: string; position: string; track: string; since: number | null };

// Each file is downloaded once per page load; every filter change reuses it.
const files = new Map<string, Promise<unknown>>();
function load<T>(path: string): Promise<T> {
  if (!files.has(path)) {
    files.set(path, fetch(path).then((r) => {
      if (!r.ok) throw new ApiError(r.status, r.status === 404 ? "Not found" : r.statusText);
      return r.json();
    }));
  }
  return files.get(path) as Promise<T>;
}

const index = () => load<Index>("/data/index.json");

// After a requested company is published, the cached index is out of date.
export function reloadIndex() {
  files.delete("/data/index.json");
}

// A subscriber's locked content per company, cached per session; resetLockedContent()
// clears it when the user signs in or out, or subscribes.
const locked = new Map<string, Promise<Locked | null>>();

export function resetLockedContent() {
  locked.clear();
}

function lockedContent(name: string): Promise<Locked | null> {
  const s = currentSession();
  if (!s) return Promise.resolve(null);
  const key = `${s.token}|${name}`;
  if (!locked.has(key)) {
    // 402 (not subscribed) or 401 (signed out) just means: show the free view
    locked.set(key, getJson<Locked>(`/api/content?company=${encodeURIComponent(name)}`).catch(() => null));
  }
  return locked.get(key)!;
}

// The public file, with a subscriber's full versions swapped in for the outlines.
async function company(name: string): Promise<CompanyFile> {
  const base = await load<CompanyFile>(`/data/${encodeURIComponent(name)}.json`);
  const full = await lockedContent(name);
  if (!full) return base;
  const swap = <T extends { id: number }>(items: T[], extra: T[]) => {
    const byId = new Map(extra.map((x) => [x.id, x]));
    return items.map((x) => byId.get(x.id) ?? x);
  };
  return { company: name, questions: swap(base.questions, full.questions),
           experiences: swap(base.experiences, full.experiences), guides: full.guides };
}

function inScope(row: { function?: string; position: string; track?: string; interview_year: number | null;
                        posted_year: number | null }, s: Scope, related: Record<string, string[]>) {
  if (row.function !== s.function) return false;
  if (s.position && row.position !== s.position) return false;
  if (s.track && !(related[s.track] ?? [s.track, "General"]).includes(row.track ?? "")) return false;
  const year = row.interview_year ?? row.posted_year;
  return !s.since || (year !== null && year >= s.since); // like SQL: an unknown year never passes
}

// ── search: the same bge-small model as the backend, run in the browser ─────────
const TRANSFORMERS_URL = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.1";
const QUERY_PREFIX = "Represent this sentence for searching relevant passages: ";
type Extractor = (text: string, opts: object) => Promise<{ data: Float32Array }>;
let extractor: Promise<Extractor> | null = null;

async function embedQuery(text: string): Promise<Float32Array> {
  // Loaded on the first search only: the library and model are ~30 MB, cached after.
  // From a CDN rather than bundled: its WebAssembly runtime is 25 MB, over Cloudflare's
  // per-file limit, and a pinned CDN copy is cached across sites anyway.
  extractor ??= import(/* @vite-ignore */ TRANSFORMERS_URL).then(
    ({ pipeline }) => pipeline("feature-extraction", "Xenova/bge-small-en-v1.5") as Promise<Extractor>,
  );
  return (await (await extractor)(QUERY_PREFIX + text, { pooling: "cls", normalize: true })).data;
}

const vectors = new WeakMap<Row, Int8Array>();
function vectorOf(q: Row): Int8Array {
  let v = vectors.get(q);
  if (!v) {
    v = Int8Array.from(atob(q.e!), (c) => (c.charCodeAt(0) << 24) >> 24); // bytes -> signed int8
    vectors.set(q, v);
  }
  return v;
}

function strip(q: Row): Question {
  const { e: _, ...rest } = q;
  return rest;
}

export async function resolveStatic(url: string): Promise<unknown> {
  const u = new URL(url, location.origin);
  const [, kind, name, what] = u.pathname.split("/").filter(Boolean).map(decodeURIComponent);
  const p = u.searchParams;
  const idx = await index();
  if (kind === "meta") return idx.meta;
  if (kind === "companies" && !name) return idx.companies;
  if (kind !== "companies") throw new ApiError(404, "Not found");

  const c = await company(name);
  const related = idx.meta.related_tracks ?? {};
  const scope: Scope = { function: p.get("function") || "Engineering", position: p.get("position") || "",
                         track: p.get("track") || "", since: p.get("since") ? Number(p.get("since")) : null };

  switch (what) {
    case "scopes": {
      // Specific questions per function/position under the track and year filters;
      // the track only narrows engineering rows (same as db.scope_counts).
      const counts = new Map<string, { function: string; position: string; questions: number }>();
      for (const q of c.questions) {
        if (!q.specific) continue;
        const s = { ...scope, function: q.function, position: "", track: q.function === "Engineering" ? scope.track : "" };
        if (!inScope(q, s, related)) continue;
        const key = `${q.function}|${q.position}`;
        const row = counts.get(key) ?? { function: q.function, position: q.position, questions: 0 };
        row.questions += 1;
        counts.set(key, row);
      }
      return [...counts.values()];
    }
    case "questions":
      return c.questions.filter((q) => inScope(q, scope, related)).map(strip);
    case "experiences":
      return c.experiences.filter((e) => inScope(e as Parameters<typeof inScope>[0], scope, related));
    case "guide": {
      const g = c.guides.find((g) => g.function === scope.function && g.position === scope.position
                                     && g.track === scope.track && (g.since ?? null) === scope.since);
      if (!g) throw new ApiError(404, "No guide for these filters yet.");
      return { markdown: g.markdown, locked: g.locked };
    }
    case "search": {
      const query = (p.get("q") ?? "").trim();
      const k = Number(p.get("k") ?? 10);
      const qv = await embedQuery(query);
      return c.questions
        .filter((q) => q.e && q.specific && inScope(q, scope, related)) // locked outlines have no embedding
        .map((q) => {
          const v = vectorOf(q);
          let dot = 0;
          for (let i = 0; i < v.length; i++) dot += v[i] * qv[i];
          return { ...strip(q), score: Math.round((dot / 127) * 1000) / 1000 };
        })
        .sort((a, b) => b.score - a.score)
        .slice(0, k);
    }
  }
  throw new ApiError(404, "Not found");
}
