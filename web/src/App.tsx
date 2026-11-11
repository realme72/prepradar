import { Fragment, useMemo, useState } from "react";
import { AccountBar, Paywall, useAccount } from "./account";
import { STATIC, apiUrl, scopeParams, type Company, type Meta, type Question, type Scope, type ScopeCount } from "./api";
import { CategoryTabs } from "./components/CategoryTabs";
import { Filters } from "./components/Filters";
import { ExperiencesTab } from "./components/ExperiencesTab";
import { GuideTab } from "./components/GuideTab";
import { LockedQuestionCard, QuestionCard } from "./components/QuestionCard";
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
  const [topic, setTopic] = useState<string | null>(null); // subtopic within the category
  const [showVague, setShowVague] = useState(false);
  const [view, setView] = useState<View>("questions");
  const [query, setQuery] = useState("");
  // Bumped after a run so every fetch below reloads with the new data.
  const [runs, setRuns] = useState(0);
  // Signing in, out, or subscribing changes what the data layer returns, too.
  const account = useAccount();
  const version = runs + account.version;

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
  const inCategory = useMemo(
    () => specific.filter((q) => category === null || q.category === category),
    [specific, category],
  );
  // Subtopics come from the tags of the questions in the chosen category, most
  // common first: under DSA that's Arrays, Graphs, Dynamic Programming, ...
  const topicCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const q of inCategory) for (const t of q.topics ?? []) c[t] = (c[t] ?? 0) + 1;
    return c;
  }, [inCategory]);
  const topicOrder = useMemo(
    () => Object.keys(topicCounts).sort((a, b) => topicCounts[b] - topicCounts[a] || a.localeCompare(b)),
    [topicCounts],
  );
  // Readable questions first, then the locked ones (the paywall goes between them).
  const visible = useMemo(
    () =>
      inCategory
        .filter((q) => topic === null || (q.topics ?? []).includes(topic))
        .sort((a, b) => Number(!!a.locked) - Number(!!b.locked) || b.times_reported - a.times_reported),
    [inCategory, topic],
  );
  const lockedCount = visible.filter((q) => q.locked).length;
  const allLocked = specific.filter((q) => q.locked).length;

  const vagueShown = useMemo(
    () => vague.filter((q) => category === null || q.category === category),
    [vague, category],
  );

  // A new category makes the old subtopic meaningless, so both change in one handler.
  function pickCategory(c: string | null) {
    setCategory(c);
    setTopic(null);
  }

  // Reset dependent state in the event handler that changes company, not in an
  // effect: it's a direct consequence of the user's action.
  function pickCompany(c: string) {
    setCompany(c);
    pickCategory(null);
    setQuery("");
  }

  // Called by RunPanel when a run finishes: show that company and refetch.
  function runFinished(c: string) {
    pickCompany(c);
    setRuns((v) => v + 1);
  }

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1>PrepRadar</h1>
          <p className="muted">Interview questions real candidates reported, by company.</p>
        </div>
        <AccountBar />
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
          pickCategory(null);
        }}
      />

      {/* The live site has no backend to run the pipeline; runs happen offline. */}
      {!STATIC && (
      <details className="run-box">
        <summary>{company ? `Refresh ${company} or add a company` : "Add a company"}</summary>
        {/* key: a new company resets the panel's local state (log, typed name) */}
        <RunPanel key={company ?? ""} initialCompany={company ?? ""} scope={scope} onFinished={runFinished} />
      </details>
      )}

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

      {company && storiesUrl && view === "experiences" && (
        <ExperiencesTab url={storiesUrl} version={version} company={company} />
      )}
      {guideUrl && view === "guide" && <GuideTab key={guideUrl} url={guideUrl} version={version} />}

      {company && view === "questions" && (
        <>
          {questions.loading && <p className="muted">Loading…</p>}
          {questions.error && <p className="error">{questions.error}</p>}
          {empty ? (
            <p className="empty">
              No {scope.position || scope.function} questions for {company} yet.
              {!STATIC && ` Fetch them with “Refresh ${company}” above.`}
            </p>
          ) : (
            <SearchBox value={query} onChange={setQuery} />
          )}

          {empty ? null : searching ? (
            <section className="list">
              {results.loading && <p className="muted">Searching…</p>}
              {results.error && <p className="error">{results.error}</p>}
              {allLocked > 0 && !account.me?.access && (
                <p className="list-note muted">Searching the questions you can see; subscribers search all {specific.length}.</p>
              )}
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
                  onSelect={pickCategory}
                />
                {category && topicOrder.length > 1 && (
                  <CategoryTabs
                    counts={topicCounts}
                    order={topicOrder}
                    active={topic}
                    onSelect={setTopic}
                    total={inCategory.length}
                    label={`${category} subtopics`}
                    className="tabs subtabs"
                  />
                )}
                {category && (
                  <p className="list-note muted">
                    {visible.length} {topic ?? category} questions, most reported first
                  </p>
                )}
                <section className="list">
                  {visible.map((q, i) => (
                    // Fragment with a key: a list item that renders two siblings.
                    <Fragment key={q.id}>
                      {q.locked && !visible[i - 1]?.locked && (
                        <Paywall what={`${lockedCount} more ${category ?? ""} questions at ${company}`.replace("  ", " ")} />
                      )}
                      {q.locked ? <LockedQuestionCard question={q} /> : <QuestionCard question={q} />}
                    </Fragment>
                  ))}
                </section>

                {vagueShown.length > 0 && (
                  <section className="vague">
                    <button className="link" onClick={() => setShowVague((v) => !v)}>
                      {showVague ? "Hide" : "Show"} {vagueShown.length} vague reports{category ? ` in ${category}` : ""}
                    </button>
                    {showVague && (
                      <ul>
                        {vagueShown.map((q) => (
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
