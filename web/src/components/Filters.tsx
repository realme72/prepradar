import type { Company } from "../api";

type Props = {
  companies: Company[];
  company: string | null;
  track: string;
  tracks: string[];
  onCompany: (c: string) => void;
  onTrack: (t: string) => void;
};

// Controlled form inputs: each <select> shows the value it's given and reports
// changes through a callback. The parent's state is the single source of truth.
export function Filters({ companies, company, track, tracks, onCompany, onTrack }: Props) {
  return (
    <div className="filters">
      <label>
        Company
        <select value={company ?? ""} onChange={(e) => onCompany(e.target.value)}>
          <option value="" disabled>Pick a company</option>
          {companies.map((c) => (
            <option key={c.company} value={c.company}>
              {c.company} ({c.questions} questions)
            </option>
          ))}
        </select>
      </label>
      <label>
        Track
        <select value={track} onChange={(e) => onTrack(e.target.value)}>
          <option value="">All tracks</option>
          {tracks.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
