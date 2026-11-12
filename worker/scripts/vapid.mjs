// Makes the key pair browser notifications are signed with (see src/push.ts).
// Prints the public key, for VAPID_PUBLIC_KEY in wrangler.jsonc; writes the private key
// to private/vapid-private.json (gitignored), for:
//   npx wrangler secret put VAPID_PRIVATE_KEY < ../private/vapid-private.json
// A new pair invalidates every existing subscription, so make it once.
import { existsSync, mkdirSync, writeFileSync } from "node:fs";

const out = decodeURIComponent(new URL("../../private/vapid-private.json", import.meta.url).pathname);
if (existsSync(out)) {
  console.error(`${out} exists already; delete it first if you really want a new pair.`);
  process.exit(1);
}
const { publicKey, privateKey } = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true,
                                                                  ["sign", "verify"]);
const raw = Buffer.from(await crypto.subtle.exportKey("raw", publicKey)).toString("base64url");
const { key_ops, ext, ...jwk } = await crypto.subtle.exportKey("jwk", privateKey);
mkdirSync(new URL("../../private/", import.meta.url), { recursive: true });
writeFileSync(out, JSON.stringify(jwk), { mode: 0o600 });
console.log(`VAPID_PUBLIC_KEY: ${raw}\nprivate key written to ${out}`);
