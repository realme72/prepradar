import { useEffect, useState } from "react";

// A custom hook: a function whose name starts with "use" and that calls other hooks.
// It packages "fetch this URL and track loading/error" so every component can reuse it.
//
// Pass null to fetch nothing (e.g. no company picked yet).
export function useApi<T>(url: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // useEffect runs after React draws the screen, and again whenever a value in the
  // dependency array ([url]) changes. Fetching belongs here, not in the component
  // body, because the body re-runs on every render.
  useEffect(() => {
    if (!url) {
      setData(null);
      return;
    }
    // If url changes mid-request (user picks another company), abort the old one
    // so a slow stale response can't overwrite the new data.
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetch(url, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? res.statusText);
        return res.json() as Promise<T>;
      })
      .then(setData)
      .catch((e: Error) => {
        if (e.name !== "AbortError") {
          setData(null);
          setError(e.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    // The cleanup function runs before the next effect, and when the component unmounts.
    return () => controller.abort();
  }, [url]);

  return { data, error, loading };
}
