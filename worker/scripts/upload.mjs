// Upload each company's subscriber-only content (private/<company>.json, written by
// `prepradar export`) to the CONTENT KV namespace as "company:<company>". Local dev store
// by default; --remote for live.
//
// Only files that changed since the last upload are sent: a "manifest" key holds each
// company's content hash. KV's free plan allows 1,000 writes a day, and every new-company
// request republishes, so re-uploading all companies each time would run out.
// --all uploads everything regardless.
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";

const dir = decodeURIComponent(new URL("../../private/", import.meta.url).pathname);
const where = process.argv.includes("--remote") ? "--remote" : "--local";
// [KV key, file path]
const files = readdirSync(dir).filter((f) => f.endsWith(".json")).map((f) => [`company:${f.slice(0, -5)}`, join(dir, f)]);
if (!files.length) {
  console.error("No locked-content files; run `uv run prepradar export` first.");
  process.exit(1);
}

const run = (args, stderr = "inherit") =>
  spawnSync("npx", ["wrangler", "kv", "key", ...args, "--binding", "CONTENT", where],
            { encoding: "utf8", stdio: ["ignore", "pipe", stderr] });

function wrangler(args) {
  const r = run(args);
  if (r.status !== 0) process.exit(r.status ?? 1);
  return r.stdout;
}

// No manifest yet (first upload) is an error on Cloudflare but not in the local store;
// either way it means "nothing uploaded so far".
let manifest = {};
if (!process.argv.includes("--all")) {
  const r = run(["get", "manifest", "--text"], "ignore");
  try {
    manifest = r.status === 0 ? JSON.parse(r.stdout) : {};
  } catch {
    manifest = {};
  }
}

const next = { ...manifest };
let sent = 0;
for (const [key, path] of files) {
  const hash = createHash("sha256").update(readFileSync(path)).digest("hex");
  if (manifest[key] === hash) continue;
  wrangler(["put", key, "--path", path]);
  next[key] = hash;
  sent += 1;
  console.log(`uploaded ${key} (${where.slice(2)})`);
}
if (sent) wrangler(["put", "manifest", JSON.stringify(next)]);
console.log(`${sent} of ${files.length} files changed`);
