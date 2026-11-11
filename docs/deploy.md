# Going live (free)

The live site is one Cloudflare Worker:

- **Static files:** the React app plus `data/*.json`, exported from your database. Search runs in the visitor's browser.
- **Four `/api` routes for payments:**
  - `checkout` creates a Razorpay order at the catalog price;
  - `verify` checks the payment with Razorpay and returns an access token;
  - `recover` returns the token again from a payment ID;
  - `unlocked` sends a pack's locked content, from KV, to token holders.

Your laptop or database is never needed to serve visitors. OpenAI and Tavily keys are only used when you run the pipeline.

```
uv run prepradar run amazon …          # refresh data (laptop, later GitHub Actions)
uv run prepradar pack amazon           # put Amazon Engineering on sale (packs/catalog.json)
uv run prepradar export                # web/public/data/*.json + packs/private/*.json
npm --prefix web run build:static      # web/dist
npm --prefix worker run data:upload -- --remote   # locked content → KV
npm --prefix worker run deploy         # site + API live
```

## 1. Test payments locally (Razorpay test mode)

1. Create a Razorpay account. Test mode works before KYC.
2. In the Dashboard, switch to **Test Mode**, then go to **Account & Settings → API Keys** and generate a test key.
3. Put the two keys in `worker/.dev.vars`, which is gitignored and was created from `.dev.vars.example`. Use `rzp_test_…` keys only.
4. Start the local Worker:
   ```
   npm --prefix web run build:static
   npm --prefix worker run data:upload
   npm --prefix worker run dev
   ```
5. Open http://localhost:8787, go to Amazon → Experiences → **Unlock**, and pay with Razorpay's published test card or test UPI ID (listed in their docs under "Test card details"). No real money moves.
6. Check that the stories unlock. Then clear site data and use **Already paid on another device?** with the `pay_…` ID from the Razorpay Dashboard → Transactions.

## 2. Deploy to Cloudflare (free plan)

1. Log in once with `npx wrangler login` (from `worker/`). It opens the browser.
2. Create the KV namespace with `npx wrangler kv namespace create PACKS`, and paste the id it prints into `worker/wrangler.jsonc`.
3. Set the secrets. Each command prompts for its value, which never goes in a file:
   ```
   npx wrangler secret put RAZORPAY_KEY_ID
   npx wrangler secret put RAZORPAY_KEY_SECRET
   npx wrangler secret put ACCESS_SECRET      # a new `openssl rand -hex 32`, not the dev one
   ```
   Start with test keys on the live URL, too.
4. Run `npm --prefix worker run data:upload -- --remote`, then `npm --prefix worker run deploy`. Wrangler prints your `*.workers.dev` URL.

## 3. Take real payments

1. Complete Razorpay KYC and activate live mode.
2. Replace both Razorpay secrets with the `rzp_live_…` pair.
3. Add your site URL under the Razorpay business website settings, since live checkout checks it.
4. Before charging, add pages for terms, a privacy policy and a refund/contact policy. Razorpay asks for them during activation.

## Safety notes

- Prices come only from `packs/catalog.json`, which is bundled into the Worker. The browser can't change the amount.
- Access tokens are signed with `ACCESS_SECRET` and last 365 days. Changing that secret signs everyone out; buyers restore access with their payment ID.
- `packs/private/` and `worker/.dev.vars` are gitignored. The repo is public, so keep it that way.
