import { useState } from "react";
import { apiUrl, type Pack } from "../api";
import { useApi } from "../hooks/useApi";
import { buyPack, Cancelled, recoverPack } from "../payments";

type Props = { company: string; packId: string; onUnlocked: () => void };

// The purchase flow as one state value. A union type makes impossible combinations
// (paying AND showing an error) unrepresentable, which separate booleans would allow.
type Status =
  | { kind: "idle" }
  | { kind: "paying" }
  | { kind: "error"; message: string }
  | { kind: "done"; title: string };

const rupees = (paise: number) => `₹${(paise / 100).toLocaleString("en-IN")}`;

export function PackOffer({ company, packId, onUnlocked }: Props) {
  const packs = useApi<Pack[]>(apiUrl(`/companies/${company}/packs`));
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [recovering, setRecovering] = useState(false);
  const [paymentId, setPaymentId] = useState("");
  const pack = packs.data?.find((p) => p.id === packId);
  if (!pack || pack.unlocked) return null;

  async function run(action: () => Promise<{ title: string }>) {
    setStatus({ kind: "paying" });
    try {
      const { title } = await action();
      setStatus({ kind: "done", title });
      onUnlocked(); // the parent bumps its version, so every list refetches with the full content
    } catch (e) {
      setStatus(e instanceof Cancelled ? { kind: "idle" } : { kind: "error", message: (e as Error).message });
    }
  }

  if (status.kind === "done") {
    return <div className="pack-offer done">Unlocked {status.title}. Thanks for supporting PrepRadar!</div>;
  }

  return (
    <div className="pack-offer">
      <div className="pack-head">
        <div>
          <span className="pack-kicker">🔒 {pack.title} pack</span>
          <p>Every candidate story with its full round-by-round timeline and advice, plus complete prep guides for
             every role and track. One-time payment, yours on this browser for a year.</p>
        </div>
        <button className="primary" disabled={status.kind === "paying"} onClick={() => run(() => buyPack(pack.id))}>
          {status.kind === "paying" ? "Waiting for payment…" : `Unlock for ${rupees(pack.price_paise)}`}
        </button>
      </div>
      {status.kind === "error" && <p className="error">{status.message}</p>}
      {recovering ? (
        <form
          className="recover"
          onSubmit={(e) => {
            e.preventDefault(); // stay on the page; we handle the submit ourselves
            run(() => recoverPack(paymentId));
          }}
        >
          <input value={paymentId} onChange={(e) => setPaymentId(e.target.value)} placeholder="pay_… from your Razorpay receipt"
                 aria-label="Payment ID" />
          <button className="link" type="submit" disabled={!paymentId.trim() || status.kind === "paying"}>Restore</button>
        </form>
      ) : (
        <button className="link small" onClick={() => setRecovering(true)}>Already paid on another device?</button>
      )}
    </div>
  );
}
