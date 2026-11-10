import { useMemo, useState } from "react";
import { apiUrl, type Company, type Meta, type Question } from "./api";
import { CategoryTabs } from "./components/CategoryTabs";
import { Filters } from "./components/Filters";
import { QuestionCard } from "./components/QuestionCard";
import { useApi } from "./hooks/useApi";

export default function App() {
  // State: values that, when changed, make React re-render this component.
  // App owns them because several children need them ("lifting state up").
  const [company, setCompany] = useState<string | null>(null);
  const [track, setTrack] = useState("Backend");
  const [category, setCategory] = useState<string | null>(null);
  const [showVague, setShowVague] = useState(false);

  const meta = useApi<Meta>(apiUrl("/meta"));
  const companies = useApi<Company[]>(apiUrl("/companies"));
  // The URL is derived from state, so picking a company/track re-runs the fetch.
  const questions = useApi<Question[]>(
    company ? apiUrl(`/companies/${company}/questions`, { track }) : null,
  );

  // Derived data: computed from state during render, never stored in state itself.
  // useMemo skips recomputing unless its inputs change.
  const specific = useMemo(() => (questions.data ?? []).filter((q) => q.specific), [questions.data]);
  const vague = useMemo(() => (questions.data ?? []).filter((q) => !q.specific), [questions.data]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const q of specific) c[q.category] = (c[q.category] ?? 0) + 1;
    return c;
  }, [specific]);
  const visible = useMemo(
    () =>
      specific
        .filter((q) => category === null || q.category === category)
        .sort((a, b) => b.times_reported - a.times_reported),
    [specific, category],
  );

  // Reset the tab in the event handler that changes company, not in an effect:
  // it's a direct consequence of the user's action.
  function pickCompany(c: string) {
    setCompany(c);
    setCategory(null);
  }

  return (
    <div className="page">
      <header className="header">
        <h1>PrepRadar</h1>
        <p className="muted">Interview questions real candidates reported, by company.</p>
      </header>

      <Filters
        companies={companies.data ?? []}
        company={company}
        track={track}
        tracks={meta.data?.tracks ?? []}
        onCompany={pickCompany}
        onTrack={(t) => {
          setTrack(t);
          setCategory(null);
        }}
      />

      {!company && <p className="empty">Pick a company to see its questions.</p>}
      {questions.loading && <p className="muted">Loading…</p>}
      {questions.error && <p className="error">{questions.error}</p>}

      {company && questions.data && (
        <>
          <CategoryTabs
            counts={counts}
            order={meta.data?.categories ?? []}
            active={category}
            onSelect={setCategory}
          />
          <section className="list">
            {visible.map((q) => (
              <QuestionCard key={q.id} question={q} />
            ))}
          </section>

          {vague.length > 0 && (
            <section className="vague">
              <button className="link" onClick={() => setShowVague((v) => !v)}>
                {showVague ? "Hide" : "Show"} {vague.length} vague reports
              </button>
              {showVague && (
                <ul>
                  {vague.map((q) => (
                    <li key={q.id}>{q.text} <span className="muted">[{q.category}]</span></li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
