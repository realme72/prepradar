# Going live (free)

The live site is one Cloudflare Worker:

- **Static files:** the React app plus `data/*.json`, exported from your database. Free visitors see half of each category's questions, 3 stories per function and guide previews. Search runs in the browser.
- **`/api` routes:**
  - **Google sign-in:** the Worker checks Google's signed token and issues its own session.
  - **₹49/month Razorpay subscriptions:** checkout, verify, cancel, and webhooks for renewals and failures.
  - **`/api/content`:** sends a company's locked content, from KV, to signed-in subscribers.

Your laptop or database is never needed to serve visitors. OpenAI and Tavily keys are only used when you run the pipeline.

```
uv run prepradar run amazon …          # refresh data (laptop, later GitHub Actions)
uv run prepradar export                # web/public/data/*.json (public) + private/*.json (subscribers)
npm --prefix web run build:static      # web/dist
npm --prefix worker run data:upload -- --remote   # private/*.json → KV
npm --prefix worker run deploy         # site + API live
```

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
2. Create the two KV namespaces and paste their ids into `worker/wrangler.jsonc`:
   ```
   npx wrangler kv namespace create CONTENT
   npx wrangler kv namespace create USERS
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
