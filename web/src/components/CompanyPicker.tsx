import { useId, useState } from "react";
import type { Company } from "../api";

type Props = {
  companies: Company[];
  company: string | null;
  onPick: (company: string) => void;
  onRequest: (name: string) => void; // a company that isn't on the site yet
};

type Option = { kind: "company"; name: string; questions: number } | { kind: "request"; name: string };

// A combobox: a text box whose list narrows as you type. Unlike a <select>, it can
// offer something that isn't in the list ("Get questions for …").
//
// The typed text is local state. App renders this with key={company}, so when the
// company changes from outside (a request finished), the box starts fresh with the
// new name instead of needing an effect to copy the prop into state.
export function CompanyPicker({ companies, company, onPick, onRequest }: Props) {
  const [text, setText] = useState(company ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0); // highlighted option, for the arrow keys
  const listId = useId(); // unique id for aria-controls, even with two pickers on a page

  // Derived on every render from the text: nothing to keep in sync.
  const query = text.trim().toLowerCase().replace(/\s+/g, " ");
  const showAll = query === "" || query === company;
  const options: Option[] = companies
    .filter((c) => showAll || c.company.includes(query))
    .map((c) => ({ kind: "company" as const, name: c.company, questions: c.questions }));
  if (query.length >= 2 && !companies.some((c) => c.company === query)) {
    options.push({ kind: "request", name: query });
  }

  function choose(o: Option) {
    setOpen(false);
    setText(o.name);
    if (o.kind === "company") onPick(o.name);
    else onRequest(o.name);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); // don't move the caret
      setOpen(true);
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((a) => (a + step + options.length) % Math.max(options.length, 1));
    } else if (e.key === "Enter" && open && options[active]) {
      choose(options[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
      setText(company ?? "");
    }
  }

  return (
    <div className="picker">
      <label htmlFor={`${listId}-input`}>Company</label>
      <input
        id={`${listId}-input`}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        spellCheck={false}
        placeholder="Search any company"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={(e) => {
          e.target.select(); // typing replaces the current name
          setOpen(true);
        }}
        onBlur={() => {
          setOpen(false);
          setText(company ?? ""); // abandoned typing goes back to the picked company
        }}
        onKeyDown={onKeyDown}
      />
      {open && options.length > 0 && (
        <ul id={listId} role="listbox" className="picker-list">
          {options.map((o, i) => (
            <li
              key={`${o.kind}:${o.name}`}
              role="option"
              aria-selected={i === active}
              className={`${o.kind === "request" ? "ask" : "company"}${i === active ? " active" : ""}`}
              // mousedown, not click: a click lands after the input's blur has closed the list
              onMouseDown={(e) => {
                e.preventDefault();
                choose(o);
              }}
              onMouseEnter={() => setActive(i)}
            >
              {o.kind === "company" ? (
                <>
                  <span>{o.name}</span>
                  <span className="muted small">{o.questions} questions</span>
                </>
              ) : (
                <span>＋ Get questions for “{o.name}”</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
