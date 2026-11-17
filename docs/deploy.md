# Going live (free)

The live site is one Cloudflare Worker:

- **Static files:** the React app plus `data/*.json`, exported from your database. Visitors who aren't subscribed (signed in or not) see each company's 2 most reported questions and its 2 newest stories. Everything else, including prep guides, is subscribers only. Search runs in the browser.
- **`/api` routes:**
  - **Google sign-in:** the Worker checks Google's signed token and issues its own session.
  - **Monthly Razorpay subscriptions (₹129 live; the site shows the plan's price):** checkout, verify, cancel, and webhooks for renewals and failures.
  - **`/api/content`:** sends a company's locked content, from KV, to signed-in subscribers.
  - **`/api/requests`:** a signed-in visitor asks for a company that isn't on the site. The Worker starts the `collect` GitHub Actions workflow, which collects it into the Neon database, then exports, rebuilds and redeploys the site. That takes about 5–12 minutes; the page waits and opens the company when it's live.

Serving visitors never needs your laptop. The database lives on Neon (free), and OpenAI and Tavily keys are only used by the collector: on your laptop, or in GitHub Actions as repository secrets.

```
visitor types "swiggy" ─▶ Worker /api/requests (signed in, under the daily caps)
                            └─▶ GitHub Actions "collect" ─▶ OpenAI + Tavily ─▶ Neon
                                    └─▶ export ─▶ build ─▶ KV upload ─▶ wrangler deploy
page polls /api/requests every 30s ─▶ "ready" once swiggy is in the published index
```

**Fast answers.** Two things keep visitors from waiting the ~10 minutes:
- **Quick live pass (`/api/quick`).** The Worker runs one web search, limited to sites where candidates post write-ups. It then streams one OpenAI call per page in parallel, so the first questions show in about 2–5 seconds and 40 are in by about 9. The result is cached for 14 days, so the next visitor gets it instantly. The full collection starts at the same time and replaces it (about 5–12 minutes). Needs the `OPENAI_API_KEY` and `TAVILY_API_KEY` Worker secrets. Caps (`QUICK_LIMIT`): 5 per user per day (15 for subscribers), 100 for the whole site.
- **Nightly pre-collection** (`.github/workflows/nightly.yml`). Each night at 02:00 IST it collects the next few companies from `companies.txt` that aren't on the site yet. The repo variable `NIGHTLY_COMPANIES` sets how many (default 5; 0 pauses it).

Caps, in `worker/src/index.ts` (`DAILY_LIMIT`): 2 new companies per signed-in user per day (5 for subscribers), 20 for the whole site. A company found empty can't be requested again for a week. Each collection costs a few rupees of OpenAI and search credit; `uv run prepradar usage` shows the totals.

```
uv run prepradar run amazon …          # refresh data (laptop, later GitHub Actions)
uv run prepradar export                # web/public/data/*.json (public) + private/*.json (subscribers)
npm --prefix web run build:static      # web/dist
npm --prefix worker run data:upload -- --remote   # private/*.json → KV
npm --prefix worker run deploy         # site + API live
```

## 0. Database on Neon (free)

1. Sign up at https://neon.tech. Create a project with the newest Postgres version, in the AWS Singapore region (closest to India).
2. Copy the connection string (`postgresql://…neon.tech/neondb?sslmode=require`).
3. Copy your local data across (pgvector is built in on Neon):
   ```
   pg_dump --no-owner --no-privileges prepradar | psql "<neon connection string>"
   ```
4. In `.env`, set `DATABASE_URL` to the Neon string. From then on, laptop runs and GitHub Actions share one database. Your local Postgres stays as a backup.

## 1. Google sign-in (free)

1. Go to https://console.cloud.google.com and create a project.
2. Go to **APIs & Services → OAuth consent screen**:
   - choose External;
   - fill in the app name and support email;
   - the only scopes needed are the defaults (openid, email, profile).
3. Go to **Credentials → Create credentials → OAuth client ID → Web application**. Under **Authorized JavaScript origins**, add:
   - `http://localhost:8787` and `http://localhost` for local testing;
   - your live URL later (e.g. `https://prepradar.<you>.workers.dev`).
4. Copy the client ID (`….apps.googleusercontent.com`) into `GOOGLE_CLIENT_ID`.

Open the local site at **http://localhost:8787**, not 127.0.0.1. Google only accepts the origins you listed.

## 2. Razorpay subscriptions (test mode first)

1. Create a Razorpay account. Test mode works before KYC.
2. In Test Mode, go to **Account & Settings → API Keys** and generate a key. That gives `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`.
3. Go to **Subscriptions → Plans → Create plan**: ₹49, monthly. Its id is `RAZORPAY_PLAN_ID`.
4. Go to **Webhooks → Add**:
   - URL: `https://<your live URL>/api/razorpay/webhook`;
   - events: all `subscription.*`;
   - type a secret, and use the same value for `RAZORPAY_WEBHOOK_SECRET`.
   - Local dev can't receive webhooks, but checkout and verify work without them.
5. Put all of these in `worker/.dev.vars` (gitignored; see `.dev.vars.example`). Then:
   ```
   npm --prefix web run build:static
   npm --prefix worker run data:upload
   npm --prefix worker run dev
   ```
6. Open http://localhost:8787, sign in with Google, and click **Subscribe**. Pay with Razorpay's test card or test UPI ID from their docs. No real money moves.

## 3. Deploy to Cloudflare (free plan)

1. In `worker/`, run `npx wrangler login`. It opens the browser.
2. Create the KV namespaces and paste their ids into `worker/wrangler.jsonc` (the ids aren't secret, so they can be committed):
   ```
   npx wrangler kv namespace create CONTENT
   npx wrangler kv namespace create USERS
   npx wrangler kv namespace create REQUESTS
   ```
3. Set the secrets. Each command prompts for its value, which never goes in a file:
   ```
   npx wrangler secret put GOOGLE_CLIENT_ID
   npx wrangler secret put RAZORPAY_KEY_ID
   npx wrangler secret put RAZORPAY_KEY_SECRET
   npx wrangler secret put RAZORPAY_PLAN_ID
   npx wrangler secret put RAZORPAY_WEBHOOK_SECRET
   npx wrangler secret put SESSION_SECRET      # a new `openssl rand -hex 32`
   ```
4. Run `npm --prefix worker run data:upload -- --remote`, then `npm --prefix worker run deploy`. Add the printed URL to Google's authorized origins and to Razorpay's webhook.

## 3b. Let visitors request companies

1. **GitHub repository secrets.** Under Settings → Secrets and variables → Actions → New repository secret, add:
   - `DATABASE_URL` (Neon);
   - `OPENAI_API_KEY`, or `GEMINI_API_KEY` to use Google's Gemini instead (see 3f);
   - `TAVILY_API_KEY`;
   - `CLOUDFLARE_ACCOUNT_ID` (shown on the Cloudflare dashboard's Workers page);
   - `CLOUDFLARE_API_TOKEN`: on Cloudflare, go to My Profile → API Tokens → Create Token and use the "Edit Cloudflare Workers" template. It lets the workflow deploy and write KV.
2. **Try it by hand:** Actions → collect → Run workflow, then type a company. When it finishes, the company is on the live site.
3. **Let the Worker start it.** Create a fine-grained GitHub token (Settings → Developer settings → Fine-grained tokens):
   - Repository access: only `prepradar`;
   - Permissions: Actions → Read and write. Nothing else.

   Then run `npx wrangler secret put GITHUB_TOKEN` in `worker/`. `GITHUB_REPO` is set in `wrangler.jsonc`.
4. For the quick live pass, give the Worker the same OpenAI and Tavily keys:
   `npx wrangler secret put OPENAI_API_KEY` and `npx wrangler secret put TAVILY_API_KEY`.
5. Create the third KV namespace: `npx wrangler kv namespace create REQUESTS`. Paste its id into `wrangler.jsonc`.

Until `GITHUB_TOKEN` is set, the site says "Requesting new companies opens soon." Without it, the companies you add from your laptop still go live with the usual export, build, upload and deploy.

## 3c. "Notify me when it's ready" (browser notifications)

While a requested company is being collected, signed-in visitors can ask for a browser
notification when it's done. It needs one key pair, made once:

    npm --prefix worker run vapid      # prints the public key, writes private/vapid-private.json

Put the public key in `wrangler.jsonc` (`VAPID_PUBLIC_KEY`), then:

    cd worker && npx wrangler secret put VAPID_PRIVATE_KEY < ../private/vapid-private.json
    npx wrangler deploy

A cron trigger (every 5 minutes) checks the companies people are waiting for and sends
the notifications. Making a new pair later cuts off every existing subscription.

## 3d. Shipping a code change (site, Worker or collector)

Don't run `wrangler deploy` from the laptop: it uploads the laptop's `web/public/data`,
an old export, and rolls the live questions back. The live site is only ever deployed
by the collect workflow's publish job, which exports fresh data from Neon first.

1. **Check it locally:**
   ```
   npm --prefix web run build          # the site compiles
   uv run pytest -q                    # collector tests (needs the local Postgres)
   npm --prefix worker test            # Worker tests
   ```
2. **Commit and push to `main`:**
   ```
   gitleaks git --staged               # no secrets in what's about to be committed
   git commit -m "..." && git push
   ```
3. **Republish:** run the collect workflow for a company that's already on the site.
   Its data is recent, so collecting takes a minute and nothing is spent on AI. The publish job then
   builds and deploys the code you just pushed.
   ```
   gh workflow run collect.yml -f company=razorpay
   gh run watch                        # pick the run; about 4–6 minutes in all
   ```
   Or on GitHub: Actions → collect → Run workflow → type `razorpay` → Run (leave "refresh" off).
4. **Check the live site** with a hard refresh (Cmd+Shift+R). If a publish was already
   running, GitHub queues yours and may show an older waiting one as "cancelled". That's
   fine, since the newest one deploys everything.

## 3e. Adding a post the collector can't read (LeetCode)

LeetCode answers automated readers with a bot check, and we don't get around it. When a
search finds a LeetCode post, the collect log says "can't be read automatically". To add one:

1. Open the post in your browser, select the whole post (title to the last line) and copy it (Cmd+C).
2. Run, with the company as it appears on the site and the post's URL:
   ```
   gh workflow run collect.yml -f company=lokal \
     -f paste_url='https://leetcode.com/discuss/post/5156361/interview-experience-of-startup-name-lok-rnxy/' \
     -f paste_text="$(pbpaste)"
   ```
3. `gh run watch`. The post gets the same checks as any page (firsthand only, duplicates
   merged, tags, the candidate's story), then the site republishes. Only what's extracted
   is stored, with the URL as the source, not the post's text.

## 3f. Using Gemini instead of OpenAI

The collector and the quick search work with either provider; Gemini goes through its
OpenAI-compatible endpoint, so the code is the same. Whichever key is set is used, and
OpenAI wins when both are, so remove the OpenAI key to switch.

1. Get a key at aistudio.google.com → Get API key. Check it (key copied):
   ```
   curl -s -o /dev/null -w "%{http_code}\n" "https://generativelanguage.googleapis.com/v1beta/models?key=$(pbpaste | tr -d '[:space:]')"
   ```
   `200` means it works.
2. Save it, and remove the OpenAI key, for the collector (GitHub) and the quick search (Worker):
   ```
   pbpaste | tr -d '[:space:]' | gh secret set GEMINI_API_KEY
   gh secret delete OPENAI_API_KEY
   cd worker && pbpaste | tr -d '[:space:]' | npx wrangler secret put GEMINI_API_KEY
   npx wrangler secret delete OPENAI_API_KEY
   ```
3. On the laptop: in `.env`, add `GEMINI_API_KEY=...` and delete the `OPENAI_API_KEY` and
   `OPENAI_MODEL` lines.

Models: `gemini-3.5-flash` for reading pages and judging, `gemini-3.5-flash-lite` for the
quick search (2.5 is closed to new keys; 3.8-flash was overloaded on 2026-11-16; the Worker's
`QUICK_MODEL` overrides it). On Gemini, 3 pages are read at once instead of 6, because the
free tier allows only a few requests a minute. A collection takes longer there.

### 3g. Free fallbacks (Gemini Flash-Lite, Groq)

The collector tries providers in order: OpenAI (if its key is set), Gemini Flash, Gemini
Flash-Lite, Groq gpt-oss-120b, Groq gpt-oss-20b. When one's daily quota runs out, the run
moves to the next and keeps going; an overload or a request too big moves just that call.
Free-tier budgets (Nov 2026): Flash ~20 requests a day, Flash-Lite ~500, each Groq model
200k tokens a day at 8k a minute (about 25 page reads, one a minute; long pages are cut).
`LLM_PROVIDERS=gemini-lite,groq` picks and orders them.

To add Groq: get a key at console.groq.com → API Keys, copy it, then
```
pbpaste | tr -d '[:space:]' | gh secret set GROQ_API_KEY
```
and add `GROQ_API_KEY=...` to `.env`. (A key you already use in another project shares its
daily quota with that project.)

## 4. Take real money

Live keys go only into the Worker's secrets. `.env` and `worker/.dev.vars` keep the
test keys, so nothing run on the laptop can charge a real card.

1. Finish KYC and the website review (it needs the terms, privacy, refund and contact
   pages). The dashboard's **Test Mode / Live Mode** switch works once Razorpay activates
   the account. Subscriptions may need activating separately: if **Subscriptions** asks
   for it in Live Mode, request it there.
2. **Switch the dashboard to Live Mode** (top bar). Everything below is per mode.
3. **API keys:** Account & Settings → API Keys → Generate Key. Copy the **Key Secret**
   (shown once; Regenerate if it's lost) and save it, then the **Key Id** (`rzp_live_…`):
   ```
   cd worker
   pbpaste | tr -d '[:space:]' | npx wrangler secret put RAZORPAY_KEY_SECRET   # secret copied
   pbpaste | tr -d '[:space:]' | npx wrangler secret put RAZORPAY_KEY_ID       # then the key id
   ```
4. **Plan:** Subscriptions → Plans → Create Plan: "PrepRadar Pro", ₹129, monthly (the test plan was ₹49)
   Copy its id (`plan_…`):
   ```
   pbpaste | tr -d '[:space:]' | npx wrangler secret put RAZORPAY_PLAN_ID
   ```
5. **Webhook:** make a new secret and copy it: `openssl rand -hex 32 | pbcopy`. Then
   Account & Settings → Webhooks → Add New Webhook:
   - URL: `https://prepradar.prepradar-worker.workers.dev/api/razorpay/webhook`
   - Secret: paste it
   - Alert email: yours
   - Events: tick every `subscription.*` event
   Save, then store the same secret (it's still on the clipboard):
   ```
   pbpaste | tr -d '[:space:]' | npx wrangler secret put RAZORPAY_WEBHOOK_SECRET
   pbcopy < /dev/null
   ```
6. Secrets take effect at once, no deploy needed. Subscribe once yourself with a real card
   or UPI, check the dashboard shows the subscription, then cancel it from the site
   (**Cancel plan**) and refund the payment from the dashboard if you like.

Subscriptions made in test mode (your own PRO, for one) stay as they are until their
paid month ends, then end, because the live keys can't find them.

## Safety notes

- The price comes from the Razorpay plan, not from the browser.
- Locked content is never in the public files. Blurred cards contain placeholder words, so "inspect element" reveals nothing.
- Stored per user: Google's numeric user id, plus subscription id, status and period end. No names, emails or passwords.
- Sessions are signed with `SESSION_SECRET` and last 30 days. Changing the secret signs everyone out; their subscriptions are kept.
- `private/` and `worker/.dev.vars` are gitignored. The repo is public, so keep it that way.
- The workflow's secrets are only readable by workflow runs on this repo. A fork's pull request can't use them, and `collect` only runs on `workflow_dispatch`.
- A requested name must match `[a-z0-9 &.'-]` and be 2–40 characters, checked in both the Worker and the workflow. It reaches shell commands only as an environment variable, never pasted into a command.
- The GitHub token can only start workflows on this one repo; it can't read code or secrets, or push.
