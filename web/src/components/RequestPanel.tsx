import { useEffect, useState } from "react";
import { ApiError, apiUrl, getJson, postJson, type CompanyRequest } from "../api";
import { GoogleButton, useAccount } from "../account";

type Props = {
  name: string;
  onReady: (company: string) => void; // it's on the site now
};

const POLL_MS = 30_000;

// A company that isn't on the site yet. Asking for it starts the collector on GitHub
// Actions (via the Worker), which takes about 10 minutes and then republishes the site.
//
// App renders this with key={name}, so a different name starts over with fresh state.
export function RequestPanel({ name, onReady }: Props) {
  const { config, session } = useAccount();
  const [request, setRequest] = useState<CompanyRequest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const status = request?.status;

  // Fetching for display belongs in an effect: on mount, see whether someone already
  // asked for this company. Then, while it's being collected, check again every 30s.
  // The effect re-runs when `status` changes, so polling stops by itself once the
  // request is no longer queued (the cleanup clears the timer).
  useEffect(() => {
    if (status && status !== "queued") return;
    let cancelled = false;
    const check = () =>
      getJson<CompanyRequest>(apiUrl("/requests", { company: name }))
        .then((r) => !cancelled && setRequest(r))
        .catch((e: Error) => !cancelled && setError(e.message));
    if (!status) check();
    const timer = status === "queued" ? setInterval(check, POLL_MS) : undefined;
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [name, status]);

  // "ready" comes from the server (the company is in the published index); telling the
  // parent is a reaction to that data, so it lives in an effect too.
  useEffect(() => {
    if (status === "ready") onReady(name);
  }, [status, name, onReady]);

  // Starting a collection is the user's action, so it happens in the click handler.
  async function start() {
    setBusy(true);
    setError(null);
    try {
      setRequest(await postJson<CompanyRequest>("/api/requests", { company: name }));
    } catch (e) {
      setError(e instanceof ApiError && e.status === 401 ? "Please sign in again." : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="request">
      <span className="pack-kicker">{name}</span>
      {status === "queued" ? (
        <>
          <p><span className="pulse" aria-hidden /> Collecting {name}: searching the web for interview write-ups, reading
             them, then publishing.</p>
          <p className="muted small">Takes about 10 minutes. This page checks every 30 seconds and opens {name} when it's
             ready. You can also come back later.</p>
        </>
      ) : status === "empty" ? (
        <p>We couldn't find interview write-ups for {name}. Check the spelling, or try the company's full name. It can be
           requested again in a week.</p>
      ) : status === "failed" ? (
        <p>Collecting {name} failed. It can be requested again in an hour.</p>
      ) : status === "none" ? (
        <>
          <p>{name} isn't on PrepRadar yet. We can search the web for interviews candidates have written up, and add
             its questions, candidate stories and a prep guide.</p>
          {!config ? (
            <p className="muted small">Requesting new companies opens soon.</p>
          ) : session ? (
            <button className="primary" disabled={busy} onClick={start}>
              {busy ? "Starting…" : `Get ${name}'s questions`}
            </button>
          ) : (
            <div className="paywall-signin request-signin">
              <span className="muted small">Sign in to request it (free, 2 companies a day)</span>
              <GoogleButton />
            </div>
          )}
        </>
      ) : !error ? (
        <p className="muted">Checking…</p>
      ) : null}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
