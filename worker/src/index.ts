// PrepRadar's only server code. Static files (the React app and its public JSON)
// are served by Cloudflare directly; requests under /api/* come here.
//
//   POST /api/checkout  {pack}                         -> a Razorpay order at the catalog price
//   POST /api/verify    {order_id, payment_id, signature} -> an access token for the pack
//   POST /api/recover   {payment_id}                   -> the same token again (new device)
//   GET  /api/unlocked?pack=…  (Authorization: Bearer <token>) -> the pack's locked content
import catalog from "../../packs/catalog.json" with { type: "json" };
import { signAccess, validPaymentSignature, verifyAccess } from "./crypto.ts";
import { HttpError, Razorpay } from "./razorpay.ts";

export type Env = {
  RAZORPAY_KEY_ID: string;
  RAZORPAY_KEY_SECRET: string;
  ACCESS_SECRET: string;
  PACKS: KVNamespace;
  ASSETS: Fetcher;
};

type Pack = { company: string; function: string; title: string; price_paise: number };
const PACKS = catalog as Record<string, Pack>;
const ACCESS_DAYS = 365;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });

async function body<T>(req: Request): Promise<T> {
  try {
    return (await req.json()) as T;
  } catch {
    throw new HttpError(400, "Expected a JSON body");
  }
}

// The price always comes from the catalog bundled into this Worker, never from the
// browser, so a visitor can't edit the amount they pay.
async function checkout(req: Request, env: Env) {
  const { pack } = await body<{ pack?: string }>(req);
  const p = pack ? PACKS[pack] : undefined;
  if (!pack || !p) throw new HttpError(404, "Unknown pack");
  const order = await new Razorpay(env.RAZORPAY_KEY_ID, env.RAZORPAY_KEY_SECRET).createOrder(
    p.price_paise,
    `${pack}-${Date.now()}`.slice(0, 40),
    { pack },
  );
  return json({ order_id: order.id, amount: order.amount, currency: order.currency, key_id: env.RAZORPAY_KEY_ID,
                title: p.title });
}

// Shared by verify and recover: ask Razorpay what really happened, then sign access to
// the pack named on the order (set by checkout, so the buyer can't pick another pack).
async function grant(env: Env, paymentId: string, expectedOrder?: string) {
  const rzp = new Razorpay(env.RAZORPAY_KEY_ID, env.RAZORPAY_KEY_SECRET);
  let payment = await rzp.payment(paymentId);
  if (expectedOrder && payment.order_id !== expectedOrder) throw new HttpError(400, "Payment is for another order");
  if (payment.status === "authorized") payment = await rzp.capture(payment);
  if (payment.status !== "captured") throw new HttpError(402, `Payment is ${payment.status}, not completed`);
  const order = await rzp.order(payment.order_id);
  const pack = order.notes?.pack;
  if (!pack || !PACKS[pack] || payment.amount < order.amount) throw new HttpError(400, "Payment doesn't match a pack");
  const expires = Math.floor(Date.now() / 1000) + ACCESS_DAYS * 86400;
  return json({ pack, title: PACKS[pack].title, token: await signAccess(env.ACCESS_SECRET, pack, expires), expires });
}

async function verify(req: Request, env: Env) {
  const b = await body<{ order_id?: string; payment_id?: string; signature?: string }>(req);
  if (!b.order_id || !b.payment_id || !b.signature) throw new HttpError(400, "Missing payment details");
  if (!(await validPaymentSignature(env.RAZORPAY_KEY_SECRET, b.order_id, b.payment_id, b.signature))) {
    throw new HttpError(400, "Payment signature doesn't match");
  }
  return grant(env, b.payment_id, b.order_id);
}

// A payment ID is only in the buyer's Razorpay receipt email, so knowing one is
// enough to restore access on a new device.
async function recover(req: Request, env: Env) {
  const { payment_id } = await body<{ payment_id?: string }>(req);
  const id = payment_id?.trim();
  if (!id || !/^pay_[A-Za-z0-9]{8,30}$/.test(id)) throw new HttpError(400, "That doesn't look like a payment ID (pay_…)");
  return grant(env, id);
}

async function unlocked(req: Request, env: Env) {
  const pack = new URL(req.url).searchParams.get("pack") ?? "";
  const token = (req.headers.get("Authorization") ?? "").replace(/^Bearer /, "");
  const granted = await verifyAccess(env.ACCESS_SECRET, token, Math.floor(Date.now() / 1000));
  if (!granted || granted !== pack) throw new HttpError(401, "No access to this pack");
  const data = await env.PACKS.get(`pack:${pack}`);
  if (!data) throw new HttpError(404, "Pack content isn't uploaded yet");
  return new Response(data, { headers: { "Content-Type": "application/json", "Cache-Control": "private, no-store" } });
}

const ROUTES: Record<string, (req: Request, env: Env) => Promise<Response>> = {
  "POST /api/checkout": checkout,
  "POST /api/verify": verify,
  "POST /api/recover": recover,
  "GET /api/unlocked": unlocked,
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
