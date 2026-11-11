// Verifies the ID token "Sign in with Google" hands the browser: an RS256-signed JWT.
// Checking the signature against Google's published keys, plus the audience, issuer and
// expiry, proves Google signed this user in to *our* client ID just now.
// https://developers.google.com/identity/gsi/web/guides/verify-google-id-token

export type GoogleUser = { sub: string; email?: string; name?: string; picture?: string };

const CERTS = "https://www.googleapis.com/oauth2/v3/certs";
const ISSUERS = new Set(["accounts.google.com", "https://accounts.google.com"]);

let keys: { at: number; jwks: Record<string, JsonWebKey> } | null = null;

// Google rotates its keys every few days; an hour's cache in this isolate is plenty.
async function googleKey(kid: string): Promise<JsonWebKey | undefined> {
  if (!keys || Date.now() - keys.at > 3600_000 || !keys.jwks[kid]) {
    const res = await fetch(CERTS);
    const { keys: list } = (await res.json()) as { keys: (JsonWebKey & { kid: string })[] };
    keys = { at: Date.now(), jwks: Object.fromEntries(list.map((k) => [k.kid, k])) };
  }
  return keys.jwks[kid];
}

const b64url = (s: string) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
const json = (s: string) => JSON.parse(new TextDecoder().decode(b64url(s)));

export async function verifyGoogleIdToken(token: string, clientId: string, now: number): Promise<GoogleUser | null> {
  const [h, p, s] = token.split(".");
  if (!h || !p || !s) return null;
  try {
    const header = json(h);
    const claims = json(p);
    if (header.alg !== "RS256") return null;
    const jwk = await googleKey(header.kid);
    if (!jwk) return null;
    const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false,
                                              ["verify"]);
    const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64url(s), new TextEncoder().encode(`${h}.${p}`));
    if (!ok || claims.aud !== clientId || !ISSUERS.has(claims.iss) || claims.exp < now || !/^\d+$/.test(claims.sub)) {
      return null;
    }
    return { sub: claims.sub, email: claims.email, name: claims.name, picture: claims.picture };
  } catch {
    return null; // malformed token
  }
}
