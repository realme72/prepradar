// HMAC helpers on the Web Crypto API (built into Workers and Node, no dependencies).

const enc = new TextEncoder();

export async function hmacHex(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(message)));
  return [...sig].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Compares every character even after a mismatch, so response timing doesn't reveal
// how much of a forged signature was right.
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

// Razorpay Checkout for a subscription returns
// signature = HMAC_SHA256(payment_id + "|" + subscription_id, key_secret).
export async function validCheckoutSignature(keySecret: string, paymentId: string, subscriptionId: string,
                                             signature: string) {
  return safeEqual(await hmacHex(keySecret, `${paymentId}|${subscriptionId}`), signature);
}

// Webhooks carry X-Razorpay-Signature = HMAC_SHA256(raw body, webhook secret).
export async function validWebhookSignature(webhookSecret: string, rawBody: string, signature: string) {
  return safeEqual(await hmacHex(webhookSecret, rawBody), signature);
}

// Session token: "<google user id>.<expiry unix seconds>.<hmac>". Google ids are digits,
// so "." is a safe separator. Stateless: checking one needs no database read.
export async function signSession(secret: string, user: string, expires: number): Promise<string> {
  return `${user}.${expires}.${await hmacHex(secret, `${user}.${expires}`)}`;
}

export async function verifySession(secret: string, token: string, now: number): Promise<string | null> {
  const [user, exp, sig] = token.split(".");
  if (!user || !exp || !sig || Number(exp) < now) return null;
  return safeEqual(await hmacHex(secret, `${user}.${exp}`), sig) ? user : null;
}
