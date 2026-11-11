// The whole purchase flow against a fake Razorpay and an in-memory KV.
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { beforeEach, test } from "node:test";
import worker, { type Env } from "../src/index.ts";

const SECRET = "rzp_secret";
let payment: Record<string, unknown>;
const orders: Record<string, Record<string, unknown>> = {};
const created: unknown[] = [];

// Stand-in for api.razorpay.com: create and read orders, read and capture payments.
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  const path = new URL(String(input)).pathname.replace("/v1", "");
  const reply = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
  if (path === "/orders" && init?.method === "POST") {
    const b = JSON.parse(String(init.body));
    created.push(b);
    const order = { id: `order_${created.length}`, ...b };
    orders[order.id] = order;
    return reply(order);
  }
  if (path.startsWith("/orders/")) return reply(orders[path.split("/")[2]]);
  if (path.endsWith("/capture")) return reply({ ...payment, status: "captured" });
  if (path.startsWith("/payments/")) return path.split("/")[2] === payment.id ? reply(payment) : reply({}, 400);
  return reply({}, 500);
}) as typeof fetch;

const kv = new Map([["pack:amazon-engineering", JSON.stringify({ pack: "amazon-engineering", experiences: [1, 2] })]]);
const env = {
  RAZORPAY_KEY_ID: "rzp_test_key",
  RAZORPAY_KEY_SECRET: SECRET,
  ACCESS_SECRET: "access_secret",
  PACKS: { get: async (k: string) => kv.get(k) ?? null },
  ASSETS: { fetch: async () => new Response("asset") },
} as unknown as Env;

// Response bodies are whatever the route returned; tests read them loosely.
const read = async (res: Response): Promise<any> => res.json();

const call = (method: string, path: string, body?: unknown, headers: Record<string, string> = {}) =>
  worker.fetch(new Request(`https://prepradar.test${path}`, {
    method, headers: { "Content-Type": "application/json", ...headers }, body: body ? JSON.stringify(body) : undefined,
  }), env);

beforeEach(() => {
  created.length = 0;
});

async function buy() {
  const order = await read(await call("POST", "/api/checkout", { pack: "amazon-engineering" }));
  payment = { id: "pay_TESTabc12345", order_id: order.order_id, amount: order.amount, currency: "INR", status: "captured" };
  const signature = createHmac("sha256", SECRET).update(`${order.order_id}|pay_TESTabc12345`).digest("hex");
  return { order, signature };
}

test("checkout charges the catalog price, whatever the browser sends", async () => {
  const res = await call("POST", "/api/checkout", { pack: "amazon-engineering", amount: 100 });
  assert.equal(res.status, 200);
  assert.deepEqual(created[0], { amount: 4900, currency: "INR", receipt: (created[0] as any).receipt,
                                 notes: { pack: "amazon-engineering" } });
  assert.equal((await call("POST", "/api/checkout", { pack: "nope" })).status, 404);
});

test("a verified payment unlocks its pack, and only with the token", async () => {
  const { order, signature } = await buy();
  const res = await call("POST", "/api/verify", { order_id: order.order_id, payment_id: "pay_TESTabc12345", signature });
  assert.equal(res.status, 200);
  const { token, pack } = await read(res);
  assert.equal(pack, "amazon-engineering");

  const ok = await call("GET", "/api/unlocked?pack=amazon-engineering", undefined, { Authorization: `Bearer ${token}` });
  assert.deepEqual(await read(ok), { pack: "amazon-engineering", experiences: [1, 2] });
  assert.equal((await call("GET", "/api/unlocked?pack=amazon-engineering")).status, 401);
  assert.equal((await call("GET", "/api/unlocked?pack=zemoso-engineering", undefined,
                           { Authorization: `Bearer ${token}` })).status, 401);
});

test("a forged signature or an unpaid payment gets nothing", async () => {
  const { order } = await buy();
  const forged = await call("POST", "/api/verify", { order_id: order.order_id, payment_id: "pay_TESTabc12345",
                                                     signature: "0".repeat(64) });
  assert.equal(forged.status, 400);
  const { order: o2, signature } = await buy();
  payment.status = "failed";
  const unpaid = await call("POST", "/api/verify", { order_id: o2.order_id, payment_id: "pay_TESTabc12345", signature });
  assert.equal(unpaid.status, 402);
});

test("recover restores access from a payment ID, and rejects junk IDs", async () => {
  await buy();
  const res = await call("POST", "/api/recover", { payment_id: " pay_TESTabc12345 " });
  assert.equal((await read(res)).pack, "amazon-engineering");
  assert.equal((await call("POST", "/api/recover", { payment_id: "pay_UNKNOWN99999" })).status, 404);
  assert.equal((await call("POST", "/api/recover", { payment_id: "../../etc" })).status, 400);
});

test("everything else is served as a static file", async () => {
  assert.equal(await (await call("GET", "/data/amazon.json")).text(), "asset");
});
