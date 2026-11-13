import { Fragment, useCallback, useMemo, useState } from "react";
import { AccountBar, Paywall, useAccount } from "./account";
import { STATIC, apiUrl, scopeParams, type Company, type Meta, type Question, type Scope, type ScopeCount } from "./api";
import { CategoryTabs } from "./components/CategoryTabs";
import { Filters } from "./components/Filters";
import { ExperiencesTab } from "./components/ExperiencesTab";
import { GuideTab } from "./components/GuideTab";
import { LockedQuestionCard, QuestionCard } from "./components/QuestionCard";
import { RequestPanel } from "./components/RequestPanel";
import { RunPanel } from "./components/RunPanel";
import { useApi } from "./hooks/useApi";
import { reloadIndex } from "./static";

type View = "questions" | "experiences" | "guide";

const DEFAULT_COMPANY = "amazon";

export default function App() {
  // State: values that, when changed, make React re-render this component.
  // App owns them because several children need them ("lifting state up").
  // A first visit opens Amazon (the company with the most questions) rather than an
  // empty page; the picker changes it.
  // A notification's link opens its company (?company=…).
  const [company, setCompany] = useState<string | null>(
    () => new URLSearchParams(window.location.search).get("company") ?? DEFAULT_COMPANY);
  // A company typed in the picker that isn't on the site yet.
  const [requested, setRequested] = useState<string | null>(null);
  // Local dev: the run box, opened by such a request with the name filled in.
  const [runOpen, setRunOpen] = useState(false);
  const [runFor, setRunFor] = useState<string | null>(null);
  // One object for every filter that narrows the questions. Grouping them means a
  // single setScope() call changes several at once (see Filters' pickFunction).
  const [scope, setScope] = useState<Scope>({ function: "Engineering", position: "", track: "Backend", since: null });
  const [category, setCategory] = useState<string | null>(null);
  const [topic, setTopic] = useState<string | null>(null); // subtopic within the category
  const [showVague, setShowVague] = useState(false);
  const [view, setView] = useState<View>("questions");
  // Bumped after a run so every fetch below reloads with the new data.
  const [runs, setRuns] = useState(0);
  // Signing in, out, or subscribing changes what the data layer returns, too.
  const account = useAccount();
  const version = runs + account.version;

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
    setRequested(null);
    pickCategory(null);
  }

  // The live site asks the Worker to collect it; local dev runs the pipeline right here.
  function requestCompany(name: string) {
    if (STATIC) {
      setCompany(null);
      setRequested(name);
    } else {
      setRunFor(name);
      setRunOpen(true);
    }
  }

  // RequestPanel calls this from an effect, so it keeps one identity across renders
  // (useCallback); a new function every render would re-run that effect each time.
  const requestReady = useCallback((c: string) => {
    reloadIndex(); // the published index now lists it
    setRuns((v) => v + 1);
    setCompany(c);
    setRequested(null);
    setCategory(null);
    setTopic(null);
  }, []);

  // Called by RunPanel when a run finishes: show that company and refetch.
  function runFinished(c: string) {
    setRunFor(null);
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
        onRequest={requestCompany}
        requested={requested}
        onScope={(s) => {
          setScope(s);
          pickCategory(null);
        }}
      />

      {/* The live site has no backend to run the pipeline; runs happen offline. */}
      {!STATIC && (
      <details className="run-box" open={runOpen} onToggle={(e) => setRunOpen(e.currentTarget.open)}>
        <summary>{company ? `Refresh ${company} or add a company` : "Add a company"}</summary>
        {/* key: a new company resets the panel's local state (log, typed name) */}
        <RunPanel key={runFor ?? company ?? ""} initialCompany={runFor ?? company ?? ""} scope={scope} onFinished={runFinished} />
      </details>
      )}

      {requested && <RequestPanel key={requested} name={requested} onReady={requestReady} />}
      {!company && !requested && (
        <p className="empty">Type a company above. If it isn't on PrepRadar yet, you can ask for it.</p>
      )}

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
