// The live site's "backend": answers the FastAPI URLs from the exported JSON in
// /data/, in the browser. Mirrors store/db.py's filters so both builds show the same
// lists. Subscribers' locked content comes from the Worker (/api/content).
import { ApiError, getJson, type Experience, type Guide, type Meta, type Question } from "./api";
import { currentSession } from "./auth";

type CompanyFile = {
  company: string;
  questions: Question[];
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
      return c.questions.filter((q) => inScope(q, scope, related));
    case "experiences":
      return c.experiences.filter((e) => inScope(e as Parameters<typeof inScope>[0], scope, related));
    case "guide": {
      const g = c.guides.find((g) => g.function === scope.function && g.position === scope.position
                                     && g.track === scope.track && (g.since ?? null) === scope.since);
      if (!g) throw new ApiError(404, "No guide for these filters yet.");
      return { markdown: g.markdown, locked: g.locked };
    }
  }
  throw new ApiError(404, "Not found");
}
