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
//   POST /api/requests {company}     collect a company that isn't on the site yet
//   GET  /api/requests?company=…     how that request is going
//   POST /api/quick {company}        quick live pass: streams a first set of questions in
//                                    seconds (NDJSON), and starts the full collection
//   GET  /api/quick?company=…        the last quick pass for a company, if any
//
// Storage is three KV namespaces: CONTENT (locked data, uploaded by `npm run data:upload`),
// USERS (one record per Google user id: their subscription, nothing else) and REQUESTS
// (companies being collected, and per-day request counts).
//
// A request starts the "collect" GitHub Actions workflow (.github/workflows/collect.yml):
// it runs the collector against the hosted database, then rebuilds and redeploys this
// site. The workflow writes the outcome back to REQUESTS when nothing was found or it failed.
import { signSession, validCheckoutSignature, validWebhookSignature, verifySession } from "./crypto.ts";
import { verifyGoogleIdToken } from "./google.ts";
import { extractQuestions, searchPages, type QuickResult } from "./quick.ts";
import { HttpError, Razorpay, type Plan, type Subscription } from "./razorpay.ts";

export type Env = {
  GOOGLE_CLIENT_ID: string;
  RAZORPAY_KEY_ID: string;
  RAZORPAY_KEY_SECRET: string;
  RAZORPAY_PLAN_ID: string;
  RAZORPAY_WEBHOOK_SECRET: string;
  SESSION_SECRET: string;
  GITHUB_TOKEN?: string; // fine-grained token: Actions read & write on GITHUB_REPO only
  GITHUB_REPO?: string;  // "owner/name"
  OPENAI_API_KEY?: string; // quick live pass only
  TAVILY_API_KEY?: string;
  QUICK_MODEL?: string;
  CONTENT: KVNamespace;
  USERS: KVNamespace;
  REQUESTS: KVNamespace;
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
  // Half-configured (e.g. no Google client yet): the site says "opens soon" instead of
  // showing a sign-in button that can't work.
  if (!env.GOOGLE_CLIENT_ID || !env.RAZORPAY_KEY_ID || !env.RAZORPAY_PLAN_ID) {
    throw new HttpError(503, "Accounts aren't set up yet");
  }
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

// ── company requests ─────────────────────────────────────────────────────────
// Each collection costs OpenAI and search credits, so requests need a signed-in user
// and are capped per user and for the whole site, per UTC day.
export const DAILY_LIMIT = { user: 2, subscriber: 5, site: 20 };
// The quick pass is one search and one model call (under ₹1), so it allows more.
export const QUICK_LIMIT = { user: 5, subscriber: 15, site: 100 };
const QUICK_TTL = 14 * 86400; // until the full collection has long replaced it

type RequestRecord = { status: "queued" | "empty" | "failed"; at: number };
// How long an outcome stands before the company can be requested again.
const RETRY_AFTER: Record<RequestRecord["status"], number> = { queued: 3600, empty: 7 * 86400, failed: 3600 };

// Lowercase, single spaces, letters/digits and a few joiners: what the collector and the
// data file names expect. Anything else is refused, not cleaned up.
export function companyName(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const name = raw.trim().toLowerCase().replace(/\s+/g, " ");
  return /^[a-z0-9][a-z0-9 &.'-]{0,38}[a-z0-9.]$/.test(name) ? name : null;
}

async function onSite(req: Request, env: Env, name: string): Promise<boolean> {
  const res = await env.ASSETS.fetch(new Request(new URL("/data/index.json", req.url)));
  if (!res.ok) return false;
  const index = (await res.json()) as { companies: { company: string }[] };
  return index.companies.some((c) => c.company === name);
}

async function requestState(req: Request, env: Env, name: string) {
  if (await onSite(req, env, name)) return { company: name, status: "ready" };
  const r = await env.REQUESTS.get<RequestRecord>(`company:${name}`, "json");
  return r && now() - r.at < RETRY_AFTER[r.status] ? { company: name, ...r } : { company: name, status: "none" };
}

async function count(env: Env, key: string): Promise<number> {
  return Number((await env.REQUESTS.get(key)) ?? 0);
}

async function requestStatus(req: Request, env: Env) {
  const name = companyName(new URL(req.url).searchParams.get("company"));
  if (!name) throw new HttpError(400, "That doesn't look like a company name");
  return json(await requestState(req, env, name));
}

const today = () => new Date().toISOString().slice(0, 10);

// Within a cap, or a 429 naming it. Returns the commit that records one more use.
async function underCap(env: Env, kind: string, user: string, limits: { user: number; subscriber: number; site: number },
                        what: string) {
  const userKey = `${kind}:${today()}:${user}`, siteKey = `${kind}:${today()}:site`;
  const [mine, site] = [await count(env, userKey), await count(env, siteKey)];
  const limit = hasAccess(await current(env, user), now()) ? limits.subscriber : limits.user;
  if (mine >= limit) throw new HttpError(429, `You can ${what} ${limit} times a day. Try again tomorrow.`);
  if (site >= limits.site) throw new HttpError(429, `Today's ${what === "request a new company" ? "new-company requests" : "quick searches"} are used up. Try again tomorrow.`);
  const ttl = { expirationTtl: 2 * 86400 };
  return () => Promise.all([env.REQUESTS.put(userKey, String(mine + 1), ttl), env.REQUESTS.put(siteKey, String(site + 1), ttl)]);
}

// Starts the collect workflow for a company that isn't on the site (or reports why not).
async function startCollection(req: Request, env: Env, user: string, name: string) {
  const state = await requestState(req, env, name);
  if (state.status !== "none") return state; // on the site, being collected, or recently tried
  if (!env.GITHUB_TOKEN || !env.GITHUB_REPO) throw new HttpError(503, "Requesting new companies opens soon");

  // KV has no atomic increment, so two requests in the same instant can both pass; the
  // caps are a budget guard, not an exact count.
  const used = await underCap(env, "count", user, DAILY_LIMIT, "request a new company");
  const res = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/collect.yml/dispatches`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.GITHUB_TOKEN}`, Accept: "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "prepradar-worker" },
    body: JSON.stringify({ ref: "main", inputs: { company: name } }),
  });
  if (!res.ok) {
    console.error("workflow dispatch failed", res.status, await res.text());
    throw new HttpError(502, "Couldn't start collecting. Try again later.");
  }
  const record: RequestRecord = { status: "queued", at: now() };
  await Promise.all([
    env.REQUESTS.put(`company:${name}`, JSON.stringify(record), { expirationTtl: RETRY_AFTER.empty }),
    used(),
  ]);
  return { company: name, ...record };
}

async function requestCompany(req: Request, env: Env) {
  const user = await signedInUser(req, env);
  const name = companyName((await body<{ company?: unknown }>(req)).company);
  if (!name) throw new HttpError(400, "That doesn't look like a company name");
  return json(await startCollection(req, env, user, name));
}

// ── quick live pass ──────────────────────────────────────────────────────────

const quickKey = (name: string) => `quick:${name}`;

async function quickCached(req: Request, env: Env) {
  const name = companyName(new URL(req.url).searchParams.get("company"));
  if (!name) throw new HttpError(400, "That doesn't look like a company name");
  const r = await env.REQUESTS.get(quickKey(name));
  if (!r) throw new HttpError(404, "No quick results yet");
  return new Response(r, { headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
}

// Answers with a stream of JSON lines, sent as they happen:
//   {"type":"sources","sources":[…]}  {"type":"question",…}  {"type":"collect",…}
//   {"type":"done","count":n}  or  {"type":"error","detail":…}
// A company already on the site, or with a recent quick result, gets plain JSON instead.
async function quick(req: Request, env: Env, ctx: ExecutionContext) {
  const user = await signedInUser(req, env);
  const name = companyName((await body<{ company?: unknown }>(req)).company);
  if (!name) throw new HttpError(400, "That doesn't look like a company name");
  if (await onSite(req, env, name)) return json({ company: name, status: "ready" });
  const cached = await env.REQUESTS.get<QuickResult>(quickKey(name), "json");
  if (cached) return json({ company: name, status: "cached", result: cached });
  if (!env.OPENAI_API_KEY || !env.TAVILY_API_KEY) throw new HttpError(503, "Quick search opens soon");
  const used = await underCap(env, "quick", user, QUICK_LIMIT, "run a quick search");
  const openai = env.OPENAI_API_KEY, tavily = env.TAVILY_API_KEY;

  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();
  const send = (o: unknown) => writer.write(encoder.encode(JSON.stringify(o) + "\n"));

  // The response starts streaming now; waitUntil keeps the Worker alive until the
  // work below finishes, even after the browser has its first bytes.
  ctx.waitUntil((async () => {
    const result: QuickResult = { company: name, at: now(), sources: [], questions: [] };
    try {
      await used();
      // the full collection starts alongside; its answer is just reported to the page
      const collect = startCollection(req, env, user, name)
        .then((state) => send({ type: "collect", ...state }))
        .catch((e) => send({ type: "collect", status: "unavailable", detail: e instanceof HttpError ? e.message : "Couldn't start" }));
      const pages = await searchPages(name, tavily);
      result.sources = pages.map(({ url, title, site }) => ({ url, title, site }));
      await send({ type: "sources", sources: result.sources });
      if (pages.length) {
        await extractQuestions(name, pages, openai, env.QUICK_MODEL || "gpt-4o-mini", async (q) => {
          result.questions.push(q);
          await send({ type: "question", ...q });
        });
      }
      await collect;
      if (result.questions.length) {
        await env.REQUESTS.put(quickKey(name), JSON.stringify(result), { expirationTtl: QUICK_TTL });
      }
      await send({ type: "done", count: result.questions.length });
    } catch (e) {
      console.error("quick pass failed", e);
      await send({ type: "error", detail: "The quick search failed. Try again in a minute." });
    } finally {
      await writer.close();
    }
  })());
  return new Response(readable, { headers: { "Content-Type": "application/x-ndjson", "Cache-Control": "no-store" } });
}

const ROUTES: Record<string, (req: Request, env: Env, ctx: ExecutionContext) => Promise<Response>> = {
  "GET /api/config": config,
  "POST /api/session": session,
  "GET /api/me": me,
  "POST /api/subscribe": subscribe,
  "POST /api/subscription/verify": verify,
  "POST /api/subscription/cancel": cancel,
  "POST /api/razorpay/webhook": webhook,
  "GET /api/content": content,
  "POST /api/requests": requestCompany,
  "GET /api/requests": requestStatus,
  "POST /api/quick": quick,
  "GET /api/quick": quickCached,
};

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const route = ROUTES[`${req.method} ${new URL(req.url).pathname}`];
    if (!route) return env.ASSETS.fetch(req);
    try {
      return await route(req, env, ctx);
    } catch (e) {
      if (e instanceof HttpError) return json({ detail: e.message }, e.status);
      console.error(e);
      return json({ detail: "Something went wrong" }, 500);
    }
  },
} satisfies ExportedHandler<Env>;
