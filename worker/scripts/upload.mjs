// Upload each company's locked content (private/<company>.json, written by `prepradar
// export`) to the CONTENT KV namespace. Local dev store by default; --remote for live.
import { readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";

const dir = decodeURIComponent(new URL("../../private/", import.meta.url).pathname);
const where = process.argv.includes("--remote") ? "--remote" : "--local";
const files = readdirSync(dir).filter((f) => f.endsWith(".json"));
if (!files.length) {
  console.error("No pack files; run `uv run prepradar export` first.");
  process.exit(1);
}
for (const f of files) {
  const id = f.replace(/\.json$/, "");
  const r = spawnSync("npx", ["wrangler", "kv", "key", "put", `company:${id}`, "--binding", "CONTENT", "--path", join(dir, f), where],
                      { stdio: ["ignore", "ignore", "inherit"] });
  if (r.status !== 0) process.exit(r.status ?? 1);
  console.log(`uploaded company:${id} (${where.slice(2)})`);
}
