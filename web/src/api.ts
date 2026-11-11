// Shapes of the JSON the FastAPI backend returns (see src/prepradar/api.py).

export type Question = {
  id: number;
  text: string;
  specific: boolean;
  category: string;
  round: string;
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
  sources: number;
  questions: number;
  last_fetched: string;
};

export type Meta = { categories: string[]; tracks: string[] };

// Builds "/api/companies/zemoso/questions?track=Backend", skipping empty params.
export function apiUrl(path: string, params: Record<string, string | number | null | undefined> = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") qs.set(k, String(v));
  }
  const query = qs.toString();
  return `/api${path}${query ? `?${query}` : ""}`;
}

export type RunRequest = { company: string; track: string | null; refresh: boolean };

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
