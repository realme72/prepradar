// Who is signed in and whether they subscribe, shared through React context: the
// header, every paywall and the data layer all need it, and passing it as props
// through each level in between would touch every component.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { STATIC, postJson } from "./api";
import { currentSession, googleSignOut, loadGoogle, saveSession, type Session } from "./auth";
import { useApi } from "./hooks/useApi";
import { Cancelled, cancelSubscription, subscribe, type Me } from "./payments";
import { resetLockedContent } from "./static";

type Config = { google_client_id: string; razorpay_key_id: string; push_key?: string | null; plan: { amount: number; currency: string; period: string } };

type Account = {
  enabled: boolean;               // false in local dev (FastAPI): nothing is locked there
  config: Config | null;
  session: Session | null;
  me: Me | null;
  version: number;                // bumps on sign-in, sign-out and payment; data refetches on it
  signIn(credential: string): Promise<void>;
  signOut(): void;
  subscribe(): Promise<void>;
  cancel(): Promise<void>;
};

const AccountContext = createContext<Account | null>(null);

export function useAccount(): Account {
  const a = useContext(AccountContext);
  if (!a) throw new Error("useAccount must be used inside <AccountProvider>");
  return a;
}

export function AccountProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => currentSession());
  const [version, setVersion] = useState(0);
  const bump = () => setVersion((v) => v + 1);
  const config = useApi<Config>(STATIC ? "/api/config" : null);
  const me = useApi<Me>(STATIC && session ? "/api/me" : null, version);

  // An expired or revoked session (the Worker answers 401) signs the user out.
  useEffect(() => {
    if (me.status === 401) {
      saveSession(null);
      setSession(null);
    }
  }, [me.status]);

  const signIn = useCallback(async (credential: string) => {
    const r = await postJson<{ session: string; expires: number; user: Omit<Session, "token" | "expires"> }>(
      "/api/session", { credential });
    const s = { token: r.session, expires: r.expires, ...r.user };
    saveSession(s);
    setSession(s);
    resetLockedContent();
    bump();
  }, []);

  const value: Account = {
    enabled: STATIC,
    config: config.data,
    session,
    me: session ? me.data : null,
    version,
    signIn,
    signOut() {
      saveSession(null);
      setSession(null);
      googleSignOut();
      resetLockedContent();
      bump();
    },
    async subscribe() {
      if (!session) return;
      await subscribe(session);
      resetLockedContent();
      bump();
    },
    async cancel() {
      await cancelSubscription();
      bump();
    },
  };
  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>;
}

const rupees = (paise: number) => `₹${(paise / 100).toLocaleString("en-IN")}`;
export const priceLabel = (c: Config | null) => (c ? `${rupees(c.plan.amount)}/${c.plan.period === "monthly" ? "month" : c.plan.period}` : "");

// Google draws its own button into a div; a ref gives us that DOM node.
export function GoogleButton() {
  const { config, signIn } = useAccount();
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!config || !ref.current) return;
    const el = ref.current;
    loadGoogle(config.google_client_id, (cred) => signIn(cred).catch((e) => setError(e.message)))
      .then((id) => id.renderButton(el, { theme: "filled_black", size: "medium", shape: "pill", text: "signin_with" }))
      .catch((e) => setError(e.message));
  }, [config, signIn]);
  return (
    <>
      <div ref={ref} className="google-btn" />
      {error && <span className="error small">{error}</span>}
    </>
  );
}

export function AccountBar() {
  const { enabled, session, me, signOut, cancel } = useAccount();
  const [confirming, setConfirming] = useState(false);
  if (!enabled) return null;
  if (!session) return <div className="account"><GoogleButton /></div>;
  const until = me?.current_end ? new Date(me.current_end * 1000).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "";
  return (
    <div className="account">
      {session.picture && <img src={session.picture} alt="" className="avatar" referrerPolicy="no-referrer" />}
      <span className="who">{session.name ?? session.email}</span>
      {me?.access && <span className="pro">PRO</span>}
      {me?.access && me.cancel_at_end && <span className="muted small">until {until}</span>}
      {me?.access && !me.cancel_at_end && (confirming ? (
        <span className="small">
          Stop renewing? You keep access until {until}.{" "}
          <button className="link small" onClick={() => cancel().finally(() => setConfirming(false))}>Yes, cancel</button>{" "}
          <button className="link small" onClick={() => setConfirming(false)}>Keep</button>
        </span>
      ) : (
        <button className="chip cancel" onClick={() => setConfirming(true)}>Cancel plan</button>
      ))}
      <button className="chip logout" onClick={signOut}>Log out</button>
    </div>
  );
}

// Shown where locked content starts. Signed out: sign in first, so the subscription
// belongs to an account and works on any device.
export function Paywall({ what }: { what: string }) {
  const account = useAccount();
  const [state, setState] = useState<{ busy: boolean; error?: string }>({ busy: false });
  if (!account.enabled || account.me?.access) return null;
  const price = priceLabel(account.config);

  async function go() {
    setState({ busy: true });
    try {
      await account.subscribe();
      setState({ busy: false });
    } catch (e) {
      setState({ busy: false, error: e instanceof Cancelled ? undefined : (e as Error).message });
    }
  }

  return (
    <div className="paywall">
      <div className="paywall-text">
        <span className="pack-kicker">🔒 {what}</span>
        <p>Every question, every candidate story with its round-by-round timeline, and the complete prep guide, for
           all companies.{price && ` ${price}, cancel anytime.`}</p>
      </div>
      {!account.config ? (
        <span className="muted small">Subscriptions open soon.</span>
      ) : account.session ? (
        <button className="primary" disabled={state.busy} onClick={go}>
          {state.busy ? "Waiting for payment…" : `Subscribe ${price}`}
        </button>
      ) : (
        <div className="paywall-signin"><span className="muted small">Sign in to subscribe</span><GoogleButton /></div>
      )}
      {state.error && <p className="error">{state.error}</p>}
    </div>
  );
}
