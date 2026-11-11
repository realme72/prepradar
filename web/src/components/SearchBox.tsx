type Props = { value: string; onChange: (q: string) => void };

// Controlled input: it shows exactly what App holds and reports every keystroke.
// It doesn't search anything itself. App debounces the value and fetches, because
// App also decides whether to show search results or the category list.
export function SearchBox({ value, onChange }: Props) {
  return (
    <div className="search">
      {/* type="search" for the keyboard and screen readers; its built-in × is hidden in
          CSS because browsers differ (Firefox has none), and the Clear link works everywhere. */}
      <input
        type="search"
        placeholder="Search by meaning, e.g. “payment retries” or “debug a slow API”"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button className="link" onClick={() => onChange("")}>Clear</button>
      )}
    </div>
  );
}
