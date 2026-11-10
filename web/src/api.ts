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
