import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";
import { signSession, validCheckoutSignature, validWebhookSignature, verifySession } from "../src/crypto.ts";

const SECRET = "test_secret";
const hmac = (s: string, m: string) => createHmac("sha256", s).update(m).digest("hex");

test("accepts Razorpay's checkout signature and rejects a tampered one", async () => {
  const sig = hmac(SECRET, "pay_1|sub_1"); // Razorpay's documented formula, via Node's own HMAC
  assert.equal(await validCheckoutSignature(SECRET, "pay_1", "sub_1", sig), true);
  assert.equal(await validCheckoutSignature(SECRET, "pay_2", "sub_1", sig), false);
  assert.equal(await validCheckoutSignature("other", "pay_1", "sub_1", sig), false);
});

test("webhook signatures cover the exact raw body", async () => {
  const raw = '{"event":"subscription.charged"}';
  assert.equal(await validWebhookSignature("wh", raw, hmac("wh", raw)), true);
  assert.equal(await validWebhookSignature("wh", raw + " ", hmac("wh", raw)), false);
});

test("sessions name one user and expire", async () => {
  const token = await signSession(SECRET, "1234567890", 2000);
  assert.equal(await verifySession(SECRET, token, 1000), "1234567890");
  assert.equal(await verifySession(SECRET, token, 3000), null);
  assert.equal(await verifySession(SECRET, token.replace("1234567890", "1234567891"), 1000), null);
  assert.equal(await verifySession(SECRET, token.replace(".2000.", ".9999."), 1000), null);
});
