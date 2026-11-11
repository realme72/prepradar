// PrepRadar's only server code. Static files (the React app and its public JSON) are
// served by Cloudflare directly; requests under /api/* come here.
//
//   GET  /api/config                 Google client id, Razorpay key id, the plan's price
//   POST /api/session {credential}   Google ID token -> our session token
//   GET  /api/me                     the signed-in user's subscription and access
//   POST /api/subscribe              start a ₹49/month Razorpay subscription
//   POST /api/subscription/verify    confirm checkout, record the subscription
//   POST /api/subscription/cancel    stop renewing (access lasts to the period's end)
//   POST /api/razorpay/webhook       renewals, failures, cancellations from Razorpay
//   GET  /api/content?company=…      a company's locked content, for subscribers
//
// Storage is two KV namespaces: CONTENT (locked data, uploaded by `npm run data:upload`)
// and USERS (one record per Google user id: their subscription, nothing else).
import { signSession, validCheckoutSignature, validWebhookSignature, verifySession } from "./crypto.ts";
import { verifyGoogleIdToken } from "./google.ts";
import { HttpError, Razorpay, type Plan, type Subscription } from "./razorpay.ts";

export type Env = {
  GOOGLE_CLIENT_ID: string;
  RAZORPAY_KEY_ID: string;
  RAZORPAY_KEY_SECRET: string;
  RAZORPAY_PLAN_ID: string;
  RAZORPAY_WEBHOOK_SECRET: string;
  SESSION_SECRET: string;
  CONTENT: KVNamespace;
  USERS: KVNamespace;
  ASSETS: Fetcher;
};

type UserRecord = { subscription_id: string; status: string; current_end: number | null; cancel_at_end?: boolean };

const SESSION_DAYS = 30;
const now = () => Math.floor(Date.now() / 1000);

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });

async function body<T>(req: Request): Promise<T> {
  try {
    return (await req.json()) as T;
  } catch {
    throw new HttpError(400, "Expected a JSON body");
  }
}

const rzp = (env: Env) => new Razorpay(env.RAZORPAY_KEY_ID, env.RAZORPAY_KEY_SECRET);

async function signedInUser(req: Request, env: Env): Promise<string> {
  const token = (req.headers.get("Authorization") ?? "").replace(/^Bearer /, "");
  const user = token && (await verifySession(env.SESSION_SECRET, token, now()));
  if (!user) throw new HttpError(401, "Please sign in again");
  return user;
}

// Who may see locked content. "authenticated" is Razorpay's state between the first
// payment and activation. After a cancellation, a halt (renewals failed) or the last
// cycle, access lasts until the end of the period already paid for.
export function hasAccess(r: UserRecord | null, at: number): boolean {
  if (!r) return false;
  if (r.status === "active" || r.status === "authenticated") return true;
  return ["pending", "halted", "cancelled", "completed"].includes(r.status) && !!r.current_end && at < r.current_end;
}

const userKey = (user: string) => `user:${user}`;

async function record(env: Env, user: string): Promise<UserRecord | null> {
  return env.USERS.get<UserRecord>(userKey(user), "json");
}

async function save(env: Env, user: string, s: Subscription, cancelAtEnd?: boolean) {
  const prev = await record(env, user);
  const r: UserRecord = {
    subscription_id: s.id,
    status: s.status,
    current_end: s.current_end ?? null,
    cancel_at_end: cancelAtEnd ?? (prev?.subscription_id === s.id ? prev.cancel_at_end : false),
  };
  await env.USERS.put(userKey(user), JSON.stringify(r));
  return r;
}

// The record, refreshed from Razorpay when it looks out of date (an "active" period
// that has ended means we missed a renewal webhook).
async function current(env: Env, user: string): Promise<UserRecord | null> {
  const r = await record(env, user);
  if (r && r.status === "active" && r.current_end && r.current_end < now()) {
    return save(env, user, await rzp(env).subscription(r.subscription_id));
  }
  return r;
}

const meBody = (r: UserRecord | null) => ({
  access: hasAccess(r, now()),
  status: r?.status ?? null,
  current_end: r?.current_end ?? null,
  cancel_at_end: !!r?.cancel_at_end,
});

let plan: Plan | null = null; // the price rarely changes; one fetch per isolate

async function config(_req: Request, env: Env) {
  plan ??= await rzp(env).plan(env.RAZORPAY_PLAN_ID);
  return json({ google_client_id: env.GOOGLE_CLIENT_ID, razorpay_key_id: env.RAZORPAY_KEY_ID,
                plan: { amount: plan.item.amount, currency: plan.item.currency, period: plan.period } });
}

async function session(req: Request, env: Env) {
  const { credential } = await body<{ credential?: string }>(req);
  const g = credential && (await verifyGoogleIdToken(credential, env.GOOGLE_CLIENT_ID, now()));
  if (!g) throw new HttpError(401, "Google sign-in couldn't be verified");
  const expires = now() + SESSION_DAYS * 86400;
  // Name, email and picture go back to this browser for display only; nothing about
  // the person is stored except their Google user id, as the key of their record.
  return json({ session: await signSession(env.SESSION_SECRET, g.sub, expires), expires,
                user: { name: g.name, email: g.email, picture: g.picture } });
}

async function me(req: Request, env: Env) {
  return json(meBody(await current(env, await signedInUser(req, env))));
}

async function subscribe(req: Request, env: Env) {
  const user = await signedInUser(req, env);
  if (hasAccess(await current(env, user), now())) throw new HttpError(409, "You're already subscribed");
  const s = await rzp(env).createSubscription(env.RAZORPAY_PLAN_ID, user);
  await save(env, user, s);
  return json({ subscription_id: s.id, key_id: env.RAZORPAY_KEY_ID });
}

async function verify(req: Request, env: Env) {
  const user = await signedInUser(req, env);
  const b = await body<{ payment_id?: string; subscription_id?: string; signature?: string }>(req);
  if (!b.payment_id || !b.subscription_id || !b.signature) throw new HttpError(400, "Missing payment details");
  if (!(await validCheckoutSignature(env.RAZORPAY_KEY_SECRET, b.payment_id, b.subscription_id, b.signature))) {
    throw new HttpError(400, "Payment signature doesn't match");
  }
  const s = await rzp(env).subscription(b.subscription_id);
  if (s.notes?.user !== user) throw new HttpError(403, "This subscription belongs to another account");
  return json(meBody(await save(env, user, s)));
}

async function cancel(req: Request, env: Env) {
  const user = await signedInUser(req, env);
  const r = await current(env, user);
  if (!r || !hasAccess(r, now())) throw new HttpError(400, "No active subscription");
  const s = await rzp(env).cancelAtCycleEnd(r.subscription_id);
  return json(meBody(await save(env, user, s, true)));
}

// Razorpay retries a webhook until it gets a 2xx, so only a bad signature is refused.
async function webhook(req: Request, env: Env) {
  const raw = await req.text();
  const sig = req.headers.get("X-Razorpay-Signature") ?? "";
  if (!(await validWebhookSignature(env.RAZORPAY_WEBHOOK_SECRET, raw, sig))) {
    throw new HttpError(400, "Bad webhook signature");
  }
  const event = JSON.parse(raw) as { event: string; payload?: { subscription?: { entity: Subscription } } };
  const s = event.payload?.subscription?.entity;
  const user = s?.notes?.user;
  if (event.event.startsWith("subscription.") && s && user) {
    const r = await record(env, user);
    // ignore events for an older, abandoned checkout the user started before this one
    if (!r || r.subscription_id === s.id) await save(env, user, s, event.event === "subscription.cancelled" ? true : undefined);
  }
  return json({ ok: true });
}

async function content(req: Request, env: Env) {
  const user = await signedInUser(req, env);
  if (!hasAccess(await current(env, user), now())) throw new HttpError(402, "Subscribe to see everything");
  const company = new URL(req.url).searchParams.get("company") ?? "";
  const data = await env.CONTENT.get(`company:${company}`);
  if (!data) throw new HttpError(404, "Nothing locked for this company");
  return new Response(data, { headers: { "Content-Type": "application/json", "Cache-Control": "private, no-store" } });
}

const ROUTES: Record<string, (req: Request, env: Env) => Promise<Response>> = {
  "GET /api/config": config,
  "POST /api/session": session,
  "GET /api/me": me,
  "POST /api/subscribe": subscribe,
  "POST /api/subscription/verify": verify,
  "POST /api/subscription/cancel": cancel,
  "POST /api/razorpay/webhook": webhook,
  "GET /api/content": content,
};

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const route = ROUTES[`${req.method} ${new URL(req.url).pathname}`];
    if (!route) return env.ASSETS.fetch(req);
    try {
      return await route(req, env);
    } catch (e) {
      if (e instanceof HttpError) return json({ detail: e.message }, e.status);
      console.error(e);
      return json({ detail: "Something went wrong" }, 500);
    }
  },
} satisfies ExportedHandler<Env>;
