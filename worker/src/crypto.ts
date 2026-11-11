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

// Razorpay Checkout returns signature = HMAC_SHA256(order_id + "|" + payment_id, key_secret).
// A match proves the payment came through Razorpay for an order this server created.
export async function validPaymentSignature(keySecret: string, orderId: string, paymentId: string, signature: string) {
  return safeEqual(await hmacHex(keySecret, `${orderId}|${paymentId}`), signature);
}

// Access token: "<pack>.<expiry unix seconds>.<hmac>". Pack ids are [a-z0-9-], so "." is
// a safe separator. Stateless: the Worker needs no database to check it.
export async function signAccess(secret: string, pack: string, expires: number): Promise<string> {
  return `${pack}.${expires}.${await hmacHex(secret, `${pack}.${expires}`)}`;
}

export async function verifyAccess(secret: string, token: string, now: number): Promise<string | null> {
  const [pack, exp, sig] = token.split(".");
  if (!pack || !exp || !sig || Number(exp) < now) return null;
  return safeEqual(await hmacHex(secret, `${pack}.${exp}`), sig) ? pack : null;
}
