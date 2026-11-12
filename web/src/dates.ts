const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "2025-03" -> "Mar 2025"
export function monthLabel(month: string) {
  const [y, m] = month.split("-").map(Number);
  return MONTHS[m - 1] ? `${MONTHS[m - 1]} ${y}` : String(y);
}

type Dated = { interview_year: number | null; posted_year: number | null; posted_month?: string | null };

// When a question or story is from. The interview year is only set when the candidate
// stated it; the posted month comes from the write-up's page and is shown alongside it,
// since "posted Mar 2025" says more than a year alone.
export function whenLabel(d: Dated) {
  const posted = d.posted_month ? `posted ${monthLabel(d.posted_month)}` : null;
  if (d.interview_year) return posted ? `interviewed ${d.interview_year} · ${posted}` : `interviewed ${d.interview_year}`;
  return posted ?? (d.posted_year ? `posted ${d.posted_year}` : null);
}
