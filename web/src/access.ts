// Access tokens from completed purchases, one per pack, kept in this browser.
// localStorage is fine here: it's a convenience, not the record. If it's cleared (or
// blocked, as in some private windows), the buyer restores access with the payment
// ID from their Razorpay receipt, and the Worker re-checks it with Razorpay.
const KEY = "prepradar.access";

export function tokens(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}");
  } catch {
    return {};
  }
}

export function saveToken(pack: string, token: string) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...tokens(), [pack]: token }));
  } catch {
    /* storage unavailable: access lasts until the page is closed (see static.ts) */
  }
  sessionTokens[pack] = token;
}

export function dropToken(pack: string) {
  delete sessionTokens[pack];
  try {
    const t = tokens();
    delete t[pack];
    localStorage.setItem(KEY, JSON.stringify(t));
  } catch {
    /* nothing stored */
  }
}

// Tokens from this page load, for browsers that refuse localStorage.
const sessionTokens: Record<string, string> = {};

export function tokenFor(pack: string): string | undefined {
  return sessionTokens[pack] ?? tokens()[pack];
}
