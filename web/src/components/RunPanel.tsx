import { useEffect, useRef, useState } from "react";
import { streamRun, type RunEvent, type Scope } from "../api";

type Props = {
  initialCompany: string; // the selected company, as a starting value only
  scope: Scope; // the run searches for whatever the filters currently select
  onFinished: (company: string) => void;
};

type LogLine = { node: string; message: string };

// Runs the LangGraph pipeline and shows each node's decisions as they stream in.
//
// The log, status and typed company are local state: nothing else needs them,
// so they don't get lifted to App. App only hears about the end, via onFinished.
// App renders this with key={company}, so picking another company gives a fresh
// panel (React throws away a component's state when its key changes).
export function RunPanel({ initialCompany, scope, onFinished }: Props) {
  const [company, setCompany] = useState(initialCompany);
  const [refresh, setRefresh] = useState(false);
  const [log, setLog] = useState<LogLine[]>([]);
  const [status, setStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [summary, setSummary] = useState<string | null>(null);

  // useRef holds a value across renders without causing one. The controller is
  // not something we display, so it doesn't belong in state.
  const controller = useRef<AbortController | null>(null);

  // Stop listening if the panel goes away mid-run (no setState on a dead component).
  useEffect(() => () => controller.current?.abort(), []);

  async function start() {
    const name = company.trim().toLowerCase();
    if (!name) return;
    controller.current = new AbortController();
    setLog([]);
    setSummary(null);
    setStatus("running");

    const handle = (e: RunEvent) => {
      if ("error" in e) {
        setStatus("error");
        setSummary(e.error);
      } else if ("done" in e) {
        setStatus("done");
        setSummary(e.gaps.length ? `Done. Still thin: ${e.gaps.join(", ")}` : "Done. Every core category is covered.");
        onFinished(name);
      } else {
        // Functional update: build on the latest log, not the one captured when
        // start() ran. Events arrive long after this closure was created.
        setLog((prev) => [...prev, e]);
      }
    };

    try {
      await streamRun(
        {
          company: name,
          function: scope.function,
          position: scope.position || null,
          track: scope.function === "Engineering" ? scope.track || null : null,
          refresh,
        },
        handle,
        controller.current.signal,
      );
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setStatus("error");
        setSummary((err as Error).message);
      }
    }
  }

  const running = status === "running";
  return (
    <section className="run">
      <div className="run-form">
        <input
          placeholder="Company name, e.g. swiggy"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          disabled={running}
        />
        <label className="check">
          <input type="checkbox" checked={refresh} onChange={(e) => setRefresh(e.target.checked)} disabled={running} />
          search again even if data is fresh
        </label>
        <button className="primary" onClick={start} disabled={running || !company.trim()}>
          {running ? "Running…" : "Fetch & build guide"}
        </button>
      </div>
      <p className="muted run-scope">
        Searches for {scope.position || `all ${scope.function} roles`}
        {scope.function === "Engineering" && scope.track ? `, ${scope.track} track` : ""}. Change it with the filters above.
      </p>
      {log.length > 0 && (
        <ol className="run-log">
          {log.map((l, i) => (
            // Log lines never reorder or get removed, so the index is a safe key here.
            <li key={i}><span className="node">{l.node}</span> {l.message.replace(`${l.node}: `, "")}</li>
          ))}
        </ol>
      )}
      {summary && <p className={status === "error" ? "error" : "muted"}>{summary}</p>}
    </section>
  );
}
