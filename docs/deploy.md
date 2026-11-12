# Going live (free)

The live site is one Cloudflare Worker:

- **Static files:** the React app plus `data/*.json`, exported from your database. Visitors who aren't subscribed (signed in or not) see each company's 2 most reported questions and its 2 newest stories. Everything else, including prep guides, is subscribers only. Search runs in the browser.
- **`/api` routes:**
  - **Google sign-in:** the Worker checks Google's signed token and issues its own session.
  - **₹49/month Razorpay subscriptions:** checkout, verify, cancel, and webhooks for renewals and failures.
  - **`/api/content`:** sends a company's locked content, from KV, to signed-in subscribers.
  - **`/api/requests`:** a signed-in visitor asks for a company that isn't on the site. The Worker starts the `collect` GitHub Actions workflow, which collects it into the Neon database, then exports, rebuilds and redeploys the site. That takes about 15–25 minutes; the page waits and opens the company when it's live.

Serving visitors never needs your laptop. The database lives on Neon (free), and OpenAI and Tavily keys are only used by the collector: on your laptop, or in GitHub Actions as repository secrets.

```
visitor types "swiggy" ─▶ Worker /api/requests (signed in, under the daily caps)
                            └─▶ GitHub Actions "collect" ─▶ OpenAI + Tavily ─▶ Neon
                                    └─▶ export ─▶ build ─▶ KV upload ─▶ wrangler deploy
page polls /api/requests every 30s ─▶ "ready" once swiggy is in the published index
```

**Fast answers.** Two things keep visitors from waiting the ~10 minutes:
- **Quick live pass (`/api/quick`).** The Worker runs one web search, limited to sites where candidates post write-ups. It then streams one OpenAI call per page in parallel, so the first questions show in about 2–5 seconds and 40 are in by about 9. The result is cached for 14 days, so the next visitor gets it instantly. The full collection starts at the same time and replaces it (15–25 minutes). Needs the `OPENAI_API_KEY` and `TAVILY_API_KEY` Worker secrets. Caps (`QUICK_LIMIT`): 5 per user per day (15 for subscribers), 100 for the whole site.
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
   - `OPENAI_API_KEY`;
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

## 4. Take real money

1. Complete Razorpay KYC and activate live mode.
2. Create the ₹49 plan again in live mode; plan ids differ between modes.
3. Replace the four Razorpay secrets with live values.
4. Add pages for terms, a privacy policy and refunds/cancellation. Razorpay asks for them during activation, and subscriptions must explain how to cancel. The site's **Cancel plan** button stops renewal, and access lasts until the paid month ends.

## Safety notes

- The price comes from the Razorpay plan, not from the browser.
- Locked content is never in the public files. Blurred cards contain placeholder words, so "inspect element" reveals nothing.
- Stored per user: Google's numeric user id, plus subscription id, status and period end. No names, emails or passwords.
- Sessions are signed with `SESSION_SECRET` and last 30 days. Changing the secret signs everyone out; their subscriptions are kept.
- `private/` and `worker/.dev.vars` are gitignored. The repo is public, so keep it that way.
- The workflow's secrets are only readable by workflow runs on this repo. A fork's pull request can't use them, and `collect` only runs on `workflow_dispatch`.
- A requested name must match `[a-z0-9 &.'-]` and be 2–40 characters, checked in both the Worker and the workflow. It reaches shell commands only as an environment variable, never pasted into a command.
- The GitHub token can only start workflows on this one repo; it can't read code or secrets, or push.
