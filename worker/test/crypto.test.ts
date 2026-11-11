import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";
import { signAccess, validPaymentSignature, verifyAccess } from "../src/crypto.ts";

const SECRET = "test_secret";

test("accepts Razorpay's signature and rejects a tampered one", async () => {
  // what Razorpay computes on its side (documented formula), via Node's own HMAC
  const sig = createHmac("sha256", SECRET).update("order_1|pay_1").digest("hex");
  assert.equal(await validPaymentSignature(SECRET, "order_1", "pay_1", sig), true);
  assert.equal(await validPaymentSignature(SECRET, "order_1", "pay_2", sig), false);
  assert.equal(await validPaymentSignature("other_secret", "order_1", "pay_1", sig), false);
});

test("access tokens unlock only their own pack, until they expire", async () => {
  const token = await signAccess(SECRET, "amazon-engineering", 2000);
  assert.equal(await verifyAccess(SECRET, token, 1000), "amazon-engineering");
  assert.equal(await verifyAccess(SECRET, token, 3000), null); // expired
  assert.equal(await verifyAccess("other", token, 1000), null);
  const forged = token.replace("amazon-engineering", "zemoso-engineering");
  assert.equal(await verifyAccess(SECRET, forged, 1000), null);
  const extended = token.replace(".2000.", ".9999.");
  assert.equal(await verifyAccess(SECRET, extended, 1000), null);
});
