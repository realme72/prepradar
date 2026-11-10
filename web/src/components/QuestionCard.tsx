import type { Question } from "../api";

// Props are a component's inputs, like function arguments. The parent decides
// what to pass; this component only displays it. No state, no fetching: a
// "presentational" component, the easiest kind to reuse and test.
type Props = { question: Question };

function yearLabel(q: Question) {
  if (q.interview_year) return `interviewed ${q.interview_year}`;
  return q.posted_year ? `posted ${q.posted_year}` : null;
}

function hostOf(url: string) {
  return new URL(url).hostname.replace(/^www\./, "");
}

export function QuestionCard({ question: q }: Props) {
  const year = yearLabel(q);
  return (
    <article className="card">
      <p className="card-text">{q.text}</p>
      <div className="card-meta">
        {q.times_reported > 1 && <span className="badge strong">×{q.times_reported} reported</span>}
        {(q.topics ?? []).map((t) => (
          // key tells React which item is which when a list re-renders
          <span key={t} className="badge">{t}</span>
        ))}
        {q.round !== "Unknown" && <span className="muted">{q.round}</span>}
        {year && <span className="muted">{year}</span>}
        {q.score !== undefined && <span className="muted">match {q.score.toFixed(2)}</span>}
      </div>
      <div className="card-sources">
        {(q.urls ?? []).map((u) => (
          <a key={u} href={u} target="_blank" rel="noreferrer">{hostOf(u)}</a>
        ))}
      </div>
    </article>
  );
}
