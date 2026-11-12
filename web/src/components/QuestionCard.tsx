import type { Question } from "../api";
import { whenLabel } from "../dates";

// Props are a component's inputs, like function arguments. The parent decides
// what to pass; this component only displays it. No state, no fetching: a
// "presentational" component, the easiest kind to reuse and test.
type Props = { question: Question };

function hostOf(url: string) {
  return new URL(url).hostname.replace(/^www\./, "");
}

export function QuestionCard({ question: q }: Props) {
  const year = whenLabel(q);
  return (
    <article className="card">
      <p className="card-text">{q.text}</p>
      <div className="card-meta">
        {q.times_reported > 1 && <span className="badge strong">×{q.times_reported} reported</span>}
        {(q.topics ?? []).map((t) => (
          // key tells React which item is which when a list re-renders
          <span key={t} className="badge">{t}</span>
        ))}
        {q.position !== "Unknown" && <span className="muted">{q.position}</span>}
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

// Stand-in words for a locked question. The real text isn't in the page at all (it's
// not in the public data), so the blur hides nothing readable: it only shows shape.
const FILLER = ["design", "a", "system", "that", "handles", "the", "array", "given", "find", "minimum", "cost",
                "service", "graph", "with", "each", "request", "within", "queue", "and", "return", "order"];

function filler(id: number) {
  let x = id * 9301 + 49297;
  const words = [];
  for (let i = 0; i < 9 + (id % 6); i++) {
    x = (x * 9301 + 49297) % 233280;
    words.push(FILLER[x % FILLER.length]);
  }
  const text = words.join(" ");
  return text[0].toUpperCase() + text.slice(1) + ".";
}

export function LockedQuestionCard({ question: q }: Props) {
  return (
    <article className="card locked-q" aria-label="Locked question">
      <p className="card-text blurred" aria-hidden="true">{filler(q.id)}</p>
      <div className="card-meta">
        {q.times_reported > 1 && <span className="badge strong">×{q.times_reported} reported</span>}
        {(q.topics ?? []).map((t) => <span key={t} className="badge">{t}</span>)}
        {q.position !== "Unknown" && <span className="muted">{q.position}</span>}
        <span className="muted">🔒</span>
      </div>
    </article>
  );
}
