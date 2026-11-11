import { useState } from "react";
import { STATIC, type Guide } from "../api";
import { useApi } from "../hooks/useApi";
import { GuideView } from "./GuideView";
import { Paywall } from "../account";

type Props = { url: string; version: number };

// Shows the saved guide for the current filters, or offers to write one from the
// questions already stored. The parent renders this with key={url}, so changing a
// filter gives a fresh component: no leftover "Building…" or error from other filters.
export function GuideTab({ url, version }: Props) {
  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);
  // Bumped after a build so useApi refetches the guide that was just saved.
  const [built, setBuilt] = useState(0);
  const guide = useApi<Guide>(url, version + built);

  // An event handler can be async: it runs on the click, not during render, so
  // awaiting here is fine. (Fetching *for display* still belongs in an effect.)
  async function build() {
    setBuilding(true);
    setBuildError(null);
    try {
      const res = await fetch(url, { method: "POST" });
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? res.statusText);
      setBuilt((b) => b + 1);
    } catch (e) {
      setBuildError((e as Error).message);
    } finally {
      setBuilding(false);
    }
  }

  if (guide.data) {
    return (
      <>
        {guide.data.locked && <Paywall what="The rest of this guide" />}
        <GuideView markdown={guide.data.markdown} />
      </>
    );
  }
  if (guide.loading) return <p className="muted">Loading…</p>;
  if (guide.status !== 404) return guide.error ? <p className="error">{guide.error}</p> : null;

  // The live site has no server to write guides; only saved ones exist there.
  if (STATIC) return <p className="empty">No prep guide for these filters yet. Try “All roles” or another track.</p>;

  return (
    <div className="guide-empty">
      <p className="muted">No prep guide for these filters yet.</p>
      <button className="primary" onClick={build} disabled={building}>
        {building ? "Writing the guide… (about 30 seconds)" : "Build guide from current questions"}
      </button>
      {buildError && <p className="error">{buildError}</p>}
    </div>
  );
}
