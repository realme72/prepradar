// A "controlled" component: it doesn't remember which tab is active. The parent
// owns that state and passes it down as `active`; a click calls `onSelect` so
// the parent can update it. Data flows down via props, events flow up via callbacks.
type Props = {
  counts: Record<string, number>; // category -> number of questions
  order: string[];                // display order from the API
  active: string | null;          // null = "All"
  onSelect: (category: string | null) => void;
  total?: number;                 // for "All" when items can be counted twice (a question with two tags)
  label?: string;                 // what the row filters, for screen readers
  className?: string;
};

// Reused for the subtopic row under a category: same behaviour, different data.
export function CategoryTabs({ counts, order, active, onSelect, total, label = "Categories", className = "tabs" }: Props) {
  const all = total ?? Object.values(counts).reduce((a, b) => a + b, 0);
  const present = order.filter((c) => counts[c]);
  return (
    <nav className={className} aria-label={label}>
      <button className={active === null ? "tab active" : "tab"} onClick={() => onSelect(null)}>
        All <span className="count">{all}</span>
      </button>
      {present.map((c) => (
        <button key={c} className={active === c ? "tab active" : "tab"} onClick={() => onSelect(c)}>
          {c} <span className="count">{counts[c]}</span>
        </button>
      ))}
    </nav>
  );
}
