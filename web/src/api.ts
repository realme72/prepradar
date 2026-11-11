// Shapes of the JSON the FastAPI backend returns (see src/prepradar/api.py). The live
// site has no FastAPI: static.ts answers the same URLs from exported JSON files.

// True in the live build (`npm run build:static`).
export const STATIC = import.meta.env.VITE_STATIC === "1";

// An error that remembers the HTTP status, so callers can tell "no guide yet" (404)
// from "the server broke".
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// GET a JSON endpoint. In the live build, requests the static data can answer never
// leave the browser; payment routes still go to the Worker.
export async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  if (STATIC && !url.startsWith("/api/unlocked")) {
    const { resolveStatic } = await import("./static");
    return (await resolveStatic(url)) as T;
  }
  const res = await fetch(url, { signal });
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => null))?.detail ?? res.statusText);
  return res.json() as Promise<T>;
}

export async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => null))?.detail ?? res.statusText);
  return res.json() as Promise<T>;
}

export type Question = {
  id: number;
  text: string;
  specific: boolean;
  category: string;
  round: string;
  function: string;
  position: string;
  track: string;
  role: string | null;
  interview_year: number | null;
  posted_year: number | null;
  times_reported: number;
  topics: string[] | null;
  urls: string[] | null;
  score?: number; // only on search results
};

export type Company = {
  company: string;
  questions: number;
  sources?: number;
  last_fetched?: string;
};

export type Meta = {
  categories: string[];
  functions: Record<string, string[]>; // function -> its role ladder
  tracks: string[]; // engineering specialties
  related_tracks?: Record<string, string[]>; // track -> tracks whose questions also apply (static data)
};

// Something a visitor can buy: everything for one company and function.
export type Pack = { id: string; company: string; function: string; title: string; price_paise: number;
                     unlocked?: boolean };

export type Guide = { markdown: string; locked?: string }; // locked = pack id when this is a preview

// How many questions a company has per function and position (for the dropdowns).
export type Round = { name: string; kind: string; summary: string };

// One candidate's interview story (a review page gives one per reviewer).
// A locked story (static data) carries only its outline: outcome, level, round count.
export type Experience = {
  id: number;
  locked?: string; // pack id that unlocks it
  rounds_count?: number;
  function?: string;
  track?: string;
  role: string | null;
  position: string;
  interview_year: number | null;
  posted_year: number | null;
  outcome: "Offer" | "Rejected" | "Withdrew" | "Pending" | "Unknown";
  difficulty: "Easy" | "Medium" | "Hard" | "Unknown";
  duration: string | null;
  summary: string;
  rounds: Round[];
  tips: string[];
  url: string;
  site: string;
};

export type ScopeCount = { function: string; position: string; questions: number };

// The filters every question/search/guide request takes. Mirrors Scope in roles.py.
export type Scope = { function: string; position: string; track: string; since: number | null };

export function scopeParams(s: Scope) {
  return {
    function: s.function,
    position: s.position,
    track: s.function === "Engineering" ? s.track : "",
    since: s.since,
  };
}

// Builds "/api/companies/zemoso/questions?track=Backend", skipping empty params.
export function apiUrl(path: string, params: Record<string, string | number | null | undefined> = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") qs.set(k, String(v));
  }
  const query = qs.toString();
  return `/api${path}${query ? `?${query}` : ""}`;
}

export type RunRequest = {
  company: string;
  function: string;
  position: string | null;
  track: string | null;
  refresh: boolean;
};

// One Server-Sent Event from POST /api/runs.
export type RunEvent =
  | { node: string; message: string }
  | { done: true; gaps: string[] }
  | { error: string };

// EventSource only supports GET, so read the POST response body as a stream.
// SSE frames look like "data: {...}\n\n"; a network chunk can end mid-frame, so
// keep the unfinished tail in `buffer` until the rest arrives.
export async function streamRun(req: RunRequest, onEvent: (e: RunEvent) => void, signal: AbortSignal) {
  const res = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`run failed: ${res.status} ${res.statusText}`);

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      if (frame.startsWith("data: ")) onEvent(JSON.parse(frame.slice(6)));
    }
  }
}
