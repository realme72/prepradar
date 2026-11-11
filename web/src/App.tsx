import { useMemo, useState } from "react";
import { apiUrl, scopeParams, type Company, type Meta, type Question, type Scope, type ScopeCount } from "./api";
import { CategoryTabs } from "./components/CategoryTabs";
import { Filters } from "./components/Filters";
import { ExperiencesTab } from "./components/ExperiencesTab";
import { GuideTab } from "./components/GuideTab";
import { QuestionCard } from "./components/QuestionCard";
import { RunPanel } from "./components/RunPanel";
import { SearchBox } from "./components/SearchBox";
import { useApi } from "./hooks/useApi";
import { useDebounce } from "./hooks/useDebounce";

type View = "questions" | "experiences" | "guide";

export default function App() {
  // State: values that, when changed, make React re-render this component.
  // App owns them because several children need them ("lifting state up").
  const [company, setCompany] = useState<string | null>(null);
  // One object for every filter that narrows the questions. Grouping them means a
  // single setScope() call changes several at once (see Filters' pickFunction).
  const [scope, setScope] = useState<Scope>({ function: "Engineering", position: "", track: "Backend", since: null });
  const [category, setCategory] = useState<string | null>(null);
  const [showVague, setShowVague] = useState(false);
  const [view, setView] = useState<View>("questions");
  const [query, setQuery] = useState("");
  // Bumped after a run so every fetch below reloads with the new data.
  const [version, setVersion] = useState(0);

  // `query` changes on every keystroke (the input needs that); the search waits
  // until typing pauses.
  const settledQuery = useDebounce(query.trim(), 300);
  const searching = settledQuery.length >= 2;

  const meta = useApi<Meta>(apiUrl("/meta"));
  const companies = useApi<Company[]>(apiUrl("/companies"), version);
  // Counts follow the track and year filters, so "SDE 2 (15)" means 15 in the list.
  const scopeCounts = useApi<ScopeCount[]>(
    company ? apiUrl(`/companies/${company}/scopes`, { track: scope.track, since: scope.since }) : null,
    version,
  );
  // The URLs are derived from state, so changing any filter re-runs the fetches.
  const params = scopeParams(scope);
  const questions = useApi<Question[]>(
    company ? apiUrl(`/companies/${company}/questions`, params) : null,
    version,
  );
  const results = useApi<Question[]>(
    company && searching ? apiUrl(`/companies/${company}/search`, { ...params, q: settledQuery, k: 15 }) : null,
  );
  const guideUrl = company ? apiUrl(`/companies/${company}/guide`, params) : null;
  const storiesUrl = company ? apiUrl(`/companies/${company}/experiences`, params) : null;

  // Derived data: computed from state during render, never stored in state itself.
  // useMemo skips recomputing unless its inputs change.
  const specific = useMemo(() => (questions.data ?? []).filter((q) => q.specific), [questions.data]);
  const vague = useMemo(() => (questions.data ?? []).filter((q) => !q.specific), [questions.data]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const q of specific) c[q.category] = (c[q.category] ?? 0) + 1;
    return c;
  }, [specific]);
  const empty = questions.data?.length === 0;
  const visible = useMemo(
    () =>
      specific
        .filter((q) => category === null || q.category === category)
        .sort((a, b) => b.times_reported - a.times_reported),
    [specific, category],
  );

  // Reset dependent state in the event handler that changes company, not in an
  // effect: it's a direct consequence of the user's action.
  function pickCompany(c: string) {
    setCompany(c);
    setCategory(null);
    setQuery("");
  }

  // Called by RunPanel when a run finishes: show that company and refetch.
  function runFinished(c: string) {
    pickCompany(c);
    setVersion((v) => v + 1);
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
        scope={scope}
        ladders={meta.data?.functions ?? {}}
        tracks={meta.data?.tracks ?? []}
        counts={scopeCounts.data ?? []}
        onCompany={pickCompany}
        onScope={(s) => {
          setScope(s);
          setCategory(null);
        }}
      />

      <details className="run-box">
        <summary>{company ? `Refresh ${company} or add a company` : "Add a company"}</summary>
        {/* key: a new company resets the panel's local state (log, typed name) */}
        <RunPanel key={company ?? ""} initialCompany={company ?? ""} scope={scope} onFinished={runFinished} />
      </details>

      {!company && <p className="empty">Pick a company to see its questions.</p>}

      {company && (
        <nav className="views">
          <button className={view === "questions" ? "view active" : "view"} onClick={() => setView("questions")}>
            Questions
          </button>
          <button className={view === "experiences" ? "view active" : "view"} onClick={() => setView("experiences")}>
            Experiences
          </button>
          <button className={view === "guide" ? "view active" : "view"} onClick={() => setView("guide")}>
            Prep guide
          </button>
        </nav>
      )}

      {storiesUrl && view === "experiences" && <ExperiencesTab url={storiesUrl} version={version} />}
      {guideUrl && view === "guide" && <GuideTab key={guideUrl} url={guideUrl} version={version} />}

      {company && view === "questions" && (
        <>
          {questions.loading && <p className="muted">Loading…</p>}
          {questions.error && <p className="error">{questions.error}</p>}
          {empty ? (
            <p className="empty">
              No {scope.position || scope.function} questions for {company} yet. Fetch them with
              “Refresh {company}” above.
            </p>
          ) : (
            <SearchBox value={query} onChange={setQuery} />
          )}

          {empty ? null : searching ? (
            <section className="list">
              {results.loading && <p className="muted">Searching…</p>}
              {results.error && <p className="error">{results.error}</p>}
              {results.data?.length === 0 && <p className="empty">No close matches.</p>}
              {results.data?.map((q) => <QuestionCard key={q.id} question={q} />)}
            </section>
          ) : (
            questions.data && (
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
            )
          )}
        </>
      )}
    </div>
  );
}
