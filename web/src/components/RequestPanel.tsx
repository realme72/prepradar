import { useEffect, useState } from "react";
import { ApiError, apiUrl, getJson, postJson, streamQuick, type CompanyRequest, type QuickEvent, type QuickResult } from "../api";
import { GoogleButton, useAccount } from "../account";

type Props = {
  name: string;
  onReady: (company: string) => void; // the full collection is on the site now
};

type Quick = Pick<QuickResult, "sources" | "questions">;
type Phase = "idle" | "searching" | "streaming" | "done";

const POLL_MS = 30_000;

function hostOf(url: string) {
  return new URL(url).hostname.replace(/^www\./, "");
}

// A company that isn't on the site yet. Two things happen when someone asks for it:
//  - the quick pass: one web search and one AI read, streamed, so questions start
//    appearing within seconds (and are cached for the next visitor);
//  - the full collection on GitHub Actions (~10 minutes), which checks every source,
//    merges duplicates, adds candidate stories and a guide, then republishes the site.
//
// App renders this with key={name}, so a different name starts over with fresh state.
export function RequestPanel({ name, onReady }: Props) {
  const { config, session } = useAccount();
  const [request, setRequest] = useState<CompanyRequest | null>(null);
  const [quick, setQuick] = useState<Quick | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [collectNote, setCollectNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const status = request?.status;

  // On mount: has anyone already run a quick pass for this company? A 404 just means no.
  useEffect(() => {
    let cancelled = false;
    getJson<QuickResult>(apiUrl("/quick", { company: name }))
      .then((r) => {
        if (cancelled) return;
        setQuick(r);
        setPhase("done");
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [name]);

  // The full collection's status: checked on mount, then every 30s while it runs. The
  // effect re-runs when `status` changes, so polling stops by itself once it's done.
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

  // "ready" comes from the server (the company is in the published index).
  useEffect(() => {
    if (status === "ready") onReady(name);
  }, [status, name, onReady]);

  function onEvent(e: QuickEvent) {
    if (e.type === "sources") {
      setQuick({ sources: e.sources, questions: [] });
      setPhase("streaming");
    } else if (e.type === "question") {
      // functional update: events arrive faster than renders, so build on the latest state
      setQuick((q) => q && { ...q, questions: [...q.questions, { text: e.text, category: e.category, source: e.source }] });
    } else if (e.type === "collect") {
      if (e.status !== "unavailable") setRequest({ company: name, status: e.status, at: e.at });
      else setCollectNote(e.detail ?? null);
    } else if (e.type === "done") {
      setPhase("done");
    } else if (e.type === "error") {
      setError(e.detail);
      setPhase("done");
    }
  }

  // Starting is the user's action, so it happens in the click handler, not an effect.
  async function start() {
    setPhase("searching");
    setError(null);
    try {
      const r = await streamQuick(name, onEvent);
      if (r.status === "ready") onReady(name);
      if (r.status === "cached") {
        setQuick(r.result);
        setPhase("done");
        // someone else's quick pass: still ask for the full collection if nobody has
        if (status === "none") setRequest(await postJson<CompanyRequest>("/api/requests", { company: name }));
      }
    } catch (e) {
      setError(e instanceof ApiError && e.status === 401 ? "Please sign in again." : (e as Error).message);
      setPhase((p) => (p === "searching" ? "idle" : "done"));
    }
  }

  const started = phase !== "idle" || quick !== null;

  return (
    <div className="request">
      <span className="pack-kicker">{name}</span>

      {!started && (
        <>
          <p>{name} isn't on PrepRadar yet. We'll search the web for interviews candidates have written up and show
             the questions in a few seconds.</p>
          {!config ? (
            <p className="muted small">Searching new companies opens soon.</p>
          ) : session ? (
            <button className="primary" onClick={start}>Get {name}'s questions</button>
          ) : (
            <div className="paywall-signin request-signin">
              <span className="muted small">Sign in to search it (free)</span>
              <GoogleButton />
            </div>
          )}
        </>
      )}

      {phase === "searching" && (
        <p><span className="pulse" aria-hidden /> Searching the web for {name} interview write-ups…</p>
      )}

      {quick && (
        <>
          <p className="muted small">
            {phase === "streaming" && <><span className="pulse" aria-hidden /> Reading {quick.sources.length} write-ups… </>}
            {phase === "done" && `${quick.questions.length} questions from ${quick.sources.length} write-ups. `}
            Quick results: read straight from search results, not yet checked one by one.
          </p>
          {phase === "done" && quick.questions.length === 0 && (
            <p>No specific questions in what the search found. The full collection reads more pages and may still find
               some.</p>
          )}
          <section className="list quick-list">
            {quick.questions.map((q, i) => {
              const src = quick.sources[q.source];
              return (
                <article key={i} className="card">
                  <p className="card-text">{q.text}</p>
                  <div className="card-meta">
                    <span className="badge">{q.category}</span>
                    {src && <a href={src.url} target="_blank" rel="noreferrer">{hostOf(src.url)}</a>}
                  </div>
                </article>
              );
            })}
          </section>
        </>
      )}

      {status === "queued" && (
        <p className="muted small"><span className="pulse" aria-hidden /> Full analysis running: every source checked,
           duplicates merged, candidate stories and a prep guide. About 10 minutes; this page updates by itself.</p>
      )}
      {status === "empty" && (
        <p className="muted small">The full collection found no interview write-ups for {name}. Check the spelling, or
           try the company's full name.</p>
      )}
      {status === "failed" && <p className="muted small">The full collection failed. It can be retried in an hour.</p>}
      {collectNote && status === "none" && <p className="muted small">Full analysis: {collectNote}</p>}
      {started && phase === "done" && session && status === "none" && !collectNote && (
        <button className="link small" onClick={() => postJson<CompanyRequest>("/api/requests", { company: name })
          .then(setRequest).catch((e: Error) => setCollectNote(e.message))}>
          Run the full analysis
        </button>
      )}
      {started && !session && config && status === "none" && (
        <div className="paywall-signin request-signin">
          <span className="muted small">Sign in to run the full analysis</span>
          <GoogleButton />
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
