// The signed-in user's session, kept in this browser. The token is ours (signed by the
// Worker after it verified Google's sign-in), not Google's. Name and picture are only
// for the header; the server never stores them.
export type Session = { token: string; expires: number; name?: string; email?: string; picture?: string };

const KEY = "prepradar.session";

export function loadSession(): Session | null {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) ?? "null") as Session | null;
    return s && s.expires * 1000 > Date.now() ? s : null;
  } catch {
    return null; // storage blocked (some private windows): signed out on each visit
  }
}

let memory: Session | null = null; // for browsers that refuse localStorage

export function saveSession(s: Session | null) {
  memory = s;
  try {
    if (s) localStorage.setItem(KEY, JSON.stringify(s));
    else localStorage.removeItem(KEY);
  } catch {
    /* kept in memory only */
  }
}

export function currentSession(): Session | null {
  return memory ?? loadSession();
}

// Google Identity Services: Google's own script draws the button and returns a signed
// ID token, which the Worker checks against Google's public keys.
type Gis = {
  initialize(o: { client_id: string; callback: (r: { credential: string }) => void; auto_select?: boolean }): void;
  renderButton(el: HTMLElement, o: object): void;
  disableAutoSelect(): void;
};
declare global {
  interface Window {
    google?: { accounts: { id: Gis } };
  }
}

let gis: Promise<Gis> | null = null;

export function loadGoogle(clientId: string, onCredential: (credential: string) => void): Promise<Gis> {
  gis ??= new Promise<Gis>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.onload = () => {
      const id = window.google!.accounts.id;
      id.initialize({ client_id: clientId, callback: (r) => onCredential(r.credential), auto_select: false });
      resolve(id);
    };
    s.onerror = () => reject(new Error("Couldn't load Google sign-in"));
    document.head.appendChild(s);
  });
  return gis;
}

export function googleSignOut() {
  window.google?.accounts.id.disableAutoSelect(); // don't silently sign the same account back in
}
