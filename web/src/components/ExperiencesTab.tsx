import { useMemo, useState } from "react";
import type { Experience } from "../api";
import { useApi } from "../hooks/useApi";
import { PackOffer } from "./PackOffer";

type Props = { url: string; version: number; company: string; onUnlocked: () => void };
type Outcome = Experience["outcome"];

const OUTCOMES: Outcome[] = ["Offer", "Rejected", "Withdrew", "Pending", "Unknown"];

// Candidate stories for the current filters, with an outcome filter of its own.
// The outcome filter is local state: nothing outside this tab needs it, so it
// lives here rather than in App (keep state as close as possible to where it's used).
export function ExperiencesTab({ url, version, company, onUnlocked }: Props) {
  const stories = useApi<Experience[]>(url, version);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  // Derived from the fetched list, recomputed only when the list changes.
  const stats = useMemo(() => {
    const all = stories.data ?? [];
    const by = (o: Outcome) => all.filter((e) => e.outcome === o).length;
    // a locked story only carries its round count
    const rounds = (e: Experience) => e.rounds?.length ?? e.rounds_count ?? 0;
    const withRounds = all.filter((e) => rounds(e) > 0);
    const avg = withRounds.reduce((n, e) => n + rounds(e), 0) / (withRounds.length || 1);
    return { total: all.length, offers: by("Offer"), rejected: by("Rejected"), avgRounds: avg.toFixed(1), by };
  }, [stories.data]);

  const visible = (stories.data ?? []).filter((e) => outcome === null || e.outcome === outcome);
  const lockedPack = stories.data?.find((e) => e.locked)?.locked;

  if (stories.loading) return <p className="muted">Loading…</p>;
  if (stories.error) return <p className="error">{stories.error}</p>;
  if (stats.total === 0) {
    return <p className="empty">No candidate stories for these filters yet.</p>;
  }

  return (
    <>
      <div className="stats">
        <div><b>{stats.total}</b><span>write-ups</span></div>
        <div><b className="offer">{stats.offers}</b><span>offers</span></div>
        <div><b className="rejected">{stats.rejected}</b><span>rejected</span></div>
        <div><b>{stats.avgRounds}</b><span>avg rounds</span></div>
      </div>

      {lockedPack && <PackOffer company={company} packId={lockedPack} onUnlocked={onUnlocked} />}

      <nav className="tabs" aria-label="Outcome">
        <button className={outcome === null ? "tab active" : "tab"} onClick={() => setOutcome(null)}>
          All <span className="count">{stats.total}</span>
        </button>
        {OUTCOMES.filter((o) => stats.by(o) > 0).map((o) => (
          <button key={o} className={outcome === o ? "tab active" : "tab"} onClick={() => setOutcome(o)}>
            {o} <span className="count">{stats.by(o)}</span>
          </button>
        ))}
      </nav>

      <section className="list">
        {visible.map((e) => (e.locked ? <LockedCard key={e.id} story={e} /> : <ExperienceCard key={e.id} story={e} />))}
      </section>
    </>
  );
}

function LockedCard({ story: e }: { story: Experience }) {
  const year = e.interview_year ?? e.posted_year;
  return (
    <article className="card story locked">
      <div className="card-meta">
        <span className={`outcome ${e.outcome.toLowerCase()}`}>{e.outcome}</span>
        {e.position !== "Unknown" && <span className="muted">{e.position}</span>}
        {e.difficulty !== "Unknown" && <span className="muted">difficulty: {e.difficulty}</span>}
        {year && <span className="muted">{year}</span>}
      </div>
      <p className="card-text muted">🔒 {e.rounds_count} rounds, with what was asked in each and the candidate's advice.</p>
    </article>
  );
}

// Defined at module level, not inside ExperiencesTab: a component defined inside
// another is a new type on every render, so React would remount every card.
function ExperienceCard({ story: e }: { story: Experience }) {
  const year = e.interview_year ? `interviewed ${e.interview_year}` : e.posted_year ? `posted ${e.posted_year}` : null;
  return (
    <article className="card story">
      <div className="card-meta">
        <span className={`outcome ${e.outcome.toLowerCase()}`}>{e.outcome}</span>
        {e.role && <span className="badge">{e.role}</span>}
        {e.position !== "Unknown" && <span className="muted">{e.position}</span>}
        {e.difficulty !== "Unknown" && <span className="muted">difficulty: {e.difficulty}</span>}
        {e.duration && <span className="muted">{e.duration}</span>}
        {year && <span className="muted">{year}</span>}
      </div>
      <p className="card-text">{e.summary}</p>

      {e.rounds.length > 0 && (
        <ol className="timeline">
          {e.rounds.map((r, i) => (
            // Rounds have no id; their position never changes, so the index is a safe key here.
            <li key={i}>
              <span className="round-name">{r.name}</span>
              {r.kind !== "Unknown" && <span className="round-kind">{r.kind}</span>}
              <p>{r.summary}</p>
            </li>
          ))}
        </ol>
      )}

      {e.tips.length > 0 && (
        <div className="tips">
          <span>Candidate's advice</span>
          <ul>{e.tips.map((t) => <li key={t}>{t}</li>)}</ul>
        </div>
      )}

      <div className="card-sources">
        <a href={e.url} target="_blank" rel="noreferrer">{new URL(e.url).hostname.replace(/^www\./, "")}</a>
      </div>
    </article>
  );
}
