// Sign-in, subscribing, renewals and locked content, against a fake Google, a fake
// Razorpay and in-memory KV.
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { beforeEach, test } from "node:test";
import worker, { DAILY_LIMIT, companyName, hasAccess, type Env } from "../src/index.ts";

const CLIENT_ID = "test-client.apps.googleusercontent.com";
const KEY_SECRET = "rzp_secret";
const WEBHOOK_SECRET = "wh_secret";
const hmac = (s: string, m: string) => createHmac("sha256", s).update(m).digest("hex");
const now = () => Math.floor(Date.now() / 1000);

// ── fake Google: a real RSA key, so the Worker's signature check is exercised ──
const pair = (await crypto.subtle.generateKey(
  { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
  true, ["sign", "verify"],
)) as CryptoKeyPair;
const jwk = { ...(await crypto.subtle.exportKey("jwk", pair.publicKey)), kid: "k1" };
const b64url = (b: Uint8Array | string) =>
  Buffer.from(typeof b === "string" ? b : b).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function googleToken(claims: Record<string, unknown>, key = pair.privateKey) {
  const head = b64url(JSON.stringify({ alg: "RS256", kid: "k1" }));
  const body = b64url(JSON.stringify({ iss: "https://accounts.google.com", aud: CLIENT_ID, sub: "1111", exp: now() + 600,
                                       name: "Test User", email: "t@example.com", ...claims }));
  const sig = new Uint8Array(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(`${head}.${body}`)));
  return `${head}.${body}.${b64url(sig)}`;
}

// ── fake Razorpay and GitHub ──
const subs: Record<string, Record<string, unknown>> = {};
const dispatched: { url: string; body: any }[] = [];
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  const url = new URL(String(input));
  const reply = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
  if (url.hostname === "www.googleapis.com") return reply({ keys: [jwk] });
  if (url.hostname === "api.github.com") {
    dispatched.push({ url: url.pathname, body: JSON.parse(String(init?.body)) });
    return new Response(null, { status: 204 });
  }
  const path = url.pathname.replace("/v1", "");
  if (path.startsWith("/plans/")) return reply({ id: "plan_1", period: "monthly", item: { amount: 4900, currency: "INR" } });
  if (path === "/subscriptions" && init?.method === "POST") {
    const b = JSON.parse(String(init.body));
    const s = { id: `sub_${Object.keys(subs).length + 1}`, status: "created", current_end: null, ...b };
    subs[s.id] = s;
    return reply(s);
  }
  const id = path.split("/")[2];
  if (path.endsWith("/cancel")) return reply(subs[id]);
  if (path.startsWith("/subscriptions/")) return subs[id] ? reply(subs[id]) : reply({}, 400);
  return reply({}, 500);
}) as typeof fetch;

function kv() {
  const m = new Map<string, string>();
  return {
    map: m,
    get: async (k: string, type?: string) => (m.has(k) ? (type === "json" ? JSON.parse(m.get(k)!) : m.get(k)!) : null),
    put: async (k: string, v: string) => void m.set(k, v),
  };
}
const USERS = kv();
const CONTENT = kv();
const REQUESTS = kv();
CONTENT.map.set("company:amazon", JSON.stringify({ company: "amazon", questions: [{ id: 9, text: "locked" }] }));
const env = {
  GOOGLE_CLIENT_ID: CLIENT_ID, RAZORPAY_KEY_ID: "rzp_test_key", RAZORPAY_KEY_SECRET: KEY_SECRET,
  RAZORPAY_PLAN_ID: "plan_1", RAZORPAY_WEBHOOK_SECRET: WEBHOOK_SECRET, SESSION_SECRET: "session_secret",
  GITHUB_TOKEN: "gh_token", GITHUB_REPO: "me/prepradar",
  CONTENT, USERS, REQUESTS,
  ASSETS: { fetch: async (r: Request) => new Response(new URL(r.url).pathname === "/data/index.json"
    ? JSON.stringify({ companies: [{ company: "amazon", questions: 3 }] }) : "asset") },
} as unknown as Env;

const read = async (res: Response): Promise<any> => res.json();
const call = (method: string, path: string, body?: unknown, token?: string, raw?: string, headers: Record<string, string> = {}) =>
  worker.fetch(new Request(`https://prepradar.test${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...headers },
    body: raw ?? (body ? JSON.stringify(body) : undefined),
  }), env);

async function signIn(sub = "1111") {
  return (await read(await call("POST", "/api/session", { credential: await googleToken({ sub }) }))).session as string;
}

async function subscribeAndPay(token: string) {
  const { subscription_id } = await read(await call("POST", "/api/subscribe", {}, token));
  subs[subscription_id].status = "active"; // what Razorpay reports after the first charge
  subs[subscription_id].current_end = now() + 30 * 86400;
  const signature = hmac(KEY_SECRET, `pay_1|${subscription_id}`);
  return { subscription_id, res: await call("POST", "/api/subscription/verify", { payment_id: "pay_1", subscription_id, signature }, token) };
}

beforeEach(() => {
  USERS.map.clear();
  REQUESTS.map.clear();
  dispatched.length = 0;
});

test("Google sign-in gives a session; forged or foreign tokens don't", async () => {
  const res = await read(await call("POST", "/api/session", { credential: await googleToken({}) }));
  assert.ok(res.session.startsWith("1111.") && res.user.name === "Test User");
  assert.equal((await call("POST", "/api/session", { credential: await googleToken({ aud: "someone-else" }) })).status, 401);
  assert.equal((await call("POST", "/api/session", { credential: await googleToken({ exp: now() - 1 }) })).status, 401);
  const other = (await crypto.subtle.generateKey({ name: "RSASSA-PKCS1-v1_5", modulusLength: 2048,
    publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["sign", "verify"])) as CryptoKeyPair;
  assert.equal((await call("POST", "/api/session", { credential: await googleToken({}, other.privateKey) })).status, 401);
  assert.equal(USERS.map.size, 0); // signing in stores nothing
});

test("locked content needs a session and an active subscription", async () => {
  assert.equal((await call("GET", "/api/content?company=amazon")).status, 401);
  const token = await signIn();
  assert.equal((await call("GET", "/api/content?company=amazon", undefined, token)).status, 402);
  const { res } = await subscribeAndPay(token);
  assert.deepEqual(await read(res), { access: true, status: "active", current_end: (await read(await call("GET", "/api/me", undefined, token))).current_end, cancel_at_end: false });
  const content = await read(await call("GET", "/api/content?company=amazon", undefined, token));
  assert.equal(content.questions[0].text, "locked");
  // stored about the user: their subscription, keyed by Google's id; no name or email
  assert.ok(!JSON.stringify([...USERS.map]).includes("example.com") && !JSON.stringify([...USERS.map]).includes("Test User"));
});

test("a forged checkout signature, or someone else's subscription, is refused", async () => {
  const token = await signIn();
  const { subscription_id } = await read(await call("POST", "/api/subscribe", {}, token));
  const forged = await call("POST", "/api/subscription/verify", { payment_id: "pay_1", subscription_id, signature: "0".repeat(64) }, token);
  assert.equal(forged.status, 400);
  const intruder = await signIn("2222");
  const signature = hmac(KEY_SECRET, `pay_1|${subscription_id}`);
  const stolen = await call("POST", "/api/subscription/verify", { payment_id: "pay_1", subscription_id, signature }, intruder);
  assert.equal(stolen.status, 403);
});

test("webhooks keep the record current; cancelling keeps access to the period's end", async () => {
  const token = await signIn();
  const { subscription_id } = await subscribeAndPay(token);
  const send = (event: string, entity: unknown) => {
    const raw = JSON.stringify({ event, payload: { subscription: { entity } } });
    return call("POST", "/api/razorpay/webhook", undefined, undefined, raw, { "X-Razorpay-Signature": hmac(WEBHOOK_SECRET, raw) });
  };
  const ended = { ...subs[subscription_id], status: "halted", current_end: now() - 10 };
  assert.equal((await send("subscription.halted", ended)).status, 200);
  assert.equal((await read(await call("GET", "/api/me", undefined, token))).access, false);
  assert.equal((await call("POST", "/api/razorpay/webhook", undefined, undefined, "{}", { "X-Razorpay-Signature": "bad" })).status, 400);

  await send("subscription.charged", { ...subs[subscription_id], status: "active", current_end: now() + 86400 });
  const cancelled = await read(await call("POST", "/api/subscription/cancel", {}, token));
  assert.equal(cancelled.cancel_at_end, true);
  await send("subscription.cancelled", { ...subs[subscription_id], status: "cancelled", current_end: now() + 86400 });
  assert.equal((await read(await call("GET", "/api/me", undefined, token))).access, true); // paid until current_end
});

test("access rules", () => {
  const t = 1000;
  assert.equal(hasAccess(null, t), false);
  assert.equal(hasAccess({ subscription_id: "s", status: "created", current_end: null }, t), false);
  assert.equal(hasAccess({ subscription_id: "s", status: "authenticated", current_end: null }, t), true);
  assert.equal(hasAccess({ subscription_id: "s", status: "cancelled", current_end: 2000 }, t), true);
  assert.equal(hasAccess({ subscription_id: "s", status: "cancelled", current_end: 500 }, t), false);
  assert.equal(hasAccess({ subscription_id: "s", status: "expired", current_end: 2000 }, t), false);
});

test("config is unavailable until Google and Razorpay are both configured", async () => {
  const half = { ...env, GOOGLE_CLIENT_ID: "" } as Env;
  const res = await worker.fetch(new Request("https://prepradar.test/api/config"), half);
  assert.equal(res.status, 503);
});

test("config exposes only public values; other paths are static files", async () => {
  const c = await read(await call("GET", "/api/config"));
  assert.deepEqual(c, { google_client_id: CLIENT_ID, razorpay_key_id: "rzp_test_key",
                        plan: { amount: 4900, currency: "INR", period: "monthly" } });
  assert.equal(await (await call("GET", "/data/amazon.json")).text(), "asset");
});

test("company names are normalised, and anything odd is refused", () => {
  assert.equal(companyName("  Cashfree   Payments "), "cashfree payments");
  assert.equal(companyName("AT&T"), "at&t");
  for (const bad of ["", "x", "a; rm -rf /", "$(whoami)", "a".repeat(60), 42, null]) assert.equal(companyName(bad), null);
});

test("requesting a company starts the collect workflow once, within the daily caps", async () => {
  assert.equal((await call("POST", "/api/requests", { company: "Cashfree" })).status, 401); // sign in first
  const token = await signIn();
  // already on the site: nothing to collect
  assert.equal((await read(await call("POST", "/api/requests", { company: "Amazon" }, token))).status, "ready");

  const first = await read(await call("POST", "/api/requests", { company: "Cashfree" }, token));
  assert.equal(first.status, "queued");
  assert.deepEqual(dispatched, [{ url: "/repos/me/prepradar/actions/workflows/collect.yml/dispatches",
                                  body: { ref: "main", inputs: { company: "cashfree" } } }]);
  // asking again (or someone else asking) while it runs doesn't start a second run
  await call("POST", "/api/requests", { company: "cashfree" }, await signIn("2222"));
  assert.equal(dispatched.length, 1);
  assert.equal((await read(await call("GET", "/api/requests?company=cashfree"))).status, "queued");

  for (let i = 1; i < DAILY_LIMIT.user; i++) await call("POST", "/api/requests", { company: `company ${i}` }, token);
  const over = await call("POST", "/api/requests", { company: "one too many" }, token);
  assert.equal(over.status, 429);
  assert.equal(dispatched.length, DAILY_LIMIT.user);
});

test("a company found empty isn't collected again for a week", async () => {
  REQUESTS.map.set("company:nosuchco", JSON.stringify({ status: "empty", at: now() - 86400 }));
  const res = await read(await call("POST", "/api/requests", { company: "nosuchco" }, await signIn()));
  assert.equal(res.status, "empty");
  assert.equal(dispatched.length, 0);
});

test("the site-wide cap holds across users", async () => {
  REQUESTS.map.set(`count:${new Date().toISOString().slice(0, 10)}:site`, String(DAILY_LIMIT.site));
  assert.equal((await call("POST", "/api/requests", { company: "newco" }, await signIn())).status, 429);
  assert.equal(dispatched.length, 0);
});
