import type { Company, Scope, ScopeCount } from "../api";
import { CompanyPicker } from "./CompanyPicker";

type Props = {
  companies: Company[];
  company: string | null;
  scope: Scope;
  ladders: Record<string, string[]>; // function -> role ladder (from /api/meta)
  tracks: string[];
  counts: ScopeCount[]; // questions per function/position for the picked company
  onCompany: (c: string) => void;
  onRequest: (name: string) => void; // a company not on the site yet
  requested?: string | null; // that company, shown in the box while it's looked up
  onScope: (s: Scope) => void;
};

const THIS_YEAR = new Date().getFullYear();
const SINCE_OPTIONS = [1, 2, 3, 5].map((n) => THIS_YEAR - n);

// Controlled form inputs: each <select> shows the value it's given and reports
// changes through a callback. The parent's state is the single source of truth.
//
// The dropdowns depend on each other: Role's options come from the chosen
// function, and Track only exists for Engineering. Nothing here stores those
// options; they're derived from props on every render, so they can't go stale.
export function Filters({ companies, company, scope, ladders, tracks, counts, onCompany, onRequest, requested, onScope }: Props) {
  const total = (fn: string, pos?: string) =>
    counts.filter((c) => c.function === fn && (pos === undefined || c.position === pos))
      .reduce((n, c) => n + c.questions, 0);

  // Changing the function invalidates the role (an "SDE 2" isn't a Sales role), so
  // this handler resets it in the same update. One event, one consistent new scope.
  // The track is kept: scopeParams() leaves it out of requests outside engineering,
  // and switching back to Engineering finds it where the user left it.
  function pickFunction(fn: string) {
    onScope({ ...scope, function: fn, position: "" });
  }
  const engineering = scope.function === "Engineering";

  return (
    <div className="filters">
      <CompanyPicker key={company ?? requested ?? ""} companies={companies} company={company ?? requested ?? null}
                     onPick={onCompany} onRequest={onRequest} />
      <label>
        Function
        <select value={scope.function} onChange={(e) => pickFunction(e.target.value)}>
          {Object.keys(ladders).map((fn) => (
            <option key={fn} value={fn}>
              {fn}{company ? ` (${total(fn)})` : ""}
            </option>
          ))}
        </select>
      </label>
      <label>
        Role
        <select value={scope.position} onChange={(e) => onScope({ ...scope, position: e.target.value })}>
          <option value="">All roles</option>
          {(ladders[scope.function] ?? []).map((pos) => (
            <option key={pos} value={pos}>
              {pos === "Unknown" ? "Level not stated" : pos}
              {company ? ` (${total(scope.function, pos)})` : ""}
            </option>
          ))}
        </select>
      </label>
      {/* Disabled rather than removed outside engineering, so the other dropdowns
          don't jump around when the function changes. */}
      <label>
        Track
        <select
          value={engineering ? scope.track : ""}
          disabled={!engineering}
          onChange={(e) => onScope({ ...scope, track: e.target.value })}
        >
          <option value="">{engineering ? "All tracks" : "Engineering only"}</option>
          {tracks.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </label>
      <label>
        Year
        <select
          value={scope.since ?? ""}
          onChange={(e) => onScope({ ...scope, since: e.target.value ? Number(e.target.value) : null })}
        >
          <option value="">Any year</option>
          {SINCE_OPTIONS.map((y) => (
            <option key={y} value={y}>{y} or later</option>
          ))}
        </select>
      </label>
    </div>
  );
}
