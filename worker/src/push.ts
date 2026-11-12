// Browser notifications (Web Push) for "tell me when this company is ready".
//
// The push itself carries no data: encrypting a payload for each browser (RFC 8291)
// is a lot of crypto for one line of text. Instead the message waits in KV under the
// subscription, and the service worker (web/public/sw.js) fetches it when the empty
// push wakes it up. Only the VAPID signature (RFC 8292) is needed, which tells the
// browser's push service the push really comes from this site.
//
// Keys: VAPID_PUBLIC_KEY (a var; the browser needs it to subscribe) and
// VAPID_PRIVATE_KEY (a secret, the same key as a JWK). `npm run vapid` makes a pair.

// The push services of Chrome/Edge/Android, Firefox, Windows and Safari. Endpoints are
// checked against these so a request can't make the Worker post to any URL it likes.
const PUSH_HOSTS = [/^fcm\.googleapis\.com$/, /\.push\.services\.mozilla\.com$/, /\.notify\.windows\.com$/,
                    /\.push\.apple\.com$/];

export function validEndpoint(raw: unknown): string | null {
  if (typeof raw !== "string" || raw.length > 1000) return null;
  try {
    const u = new URL(raw);
    return u.protocol === "https:" && PUSH_HOSTS.some((h) => h.test(u.hostname)) ? raw : null;
  } catch {
    return null;
  }
}

export const b64url = (bytes: ArrayBuffer | Uint8Array) =>
  btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

// A short id for a subscription, to key its waiting messages.
export async function endpointId(endpoint: string) {
  return b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(endpoint))).slice(0, 32);
}

// The signed token for one push service (its origin is the token's audience).
export async function vapidToken(endpoint: string, privateJwk: string, subject: string, at: number) {
  const key = await crypto.subtle.importKey("jwk", JSON.parse(privateJwk), { name: "ECDSA", namedCurve: "P-256" },
                                            false, ["sign"]);
  const part = (o: unknown) => b64url(new TextEncoder().encode(JSON.stringify(o)));
  const unsigned = `${part({ typ: "JWT", alg: "ES256" })}.${part({ aud: new URL(endpoint).origin, exp: at + 12 * 3600, sub: subject })}`;
  // WebCrypto's ECDSA signature is already the r||s form JWS wants
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, new TextEncoder().encode(unsigned));
  return `${unsigned}.${b64url(sig)}`;
}

export type PushKeys = { publicKey: string; privateJwk: string; subject: string };

// "gone": the browser unsubscribed (or the user blocked notifications); forget it.
export async function sendPush(endpoint: string, keys: PushKeys, at: number): Promise<"sent" | "gone" | "failed"> {
  const token = await vapidToken(endpoint, keys.privateJwk, keys.subject, at);
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { Authorization: `vapid t=${token}, k=${keys.publicKey}`, TTL: String(3 * 86400), Urgency: "high",
               "Content-Length": "0" },
  });
  if (res.ok) return "sent";
  if (res.status === 404 || res.status === 410) return "gone";
  console.error("push failed", res.status, await res.text());
  return "failed";
}
