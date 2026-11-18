// The pages a payment gateway asks for: pricing, terms, privacy, refunds, delivery and
// contact. Plain views of the same app (the Worker serves index.html for any path), so
// they share the site's look and read the live price from the plan.
import type { ReactNode } from "react";
import { priceLabel, useAccount } from "../account";

// Who runs PrepRadar, as on the Razorpay account.
export const BUSINESS = {
  name: "Gaurav Bharti",
  email: "prepradar.review@gmail.com",
  address: "", // operating address, as in Razorpay KYC
  updated: "18 November 2026",
};

export const POLICY_PAGES = {
  "/pricing": "Pricing",
  "/terms": "Terms of Service",
  "/privacy": "Privacy Policy",
  "/refunds": "Cancellation & Refunds",
  "/delivery": "Delivery",
  "/contact": "Contact",
} as const;
export type PolicyPath = keyof typeof POLICY_PAGES;

export const isPolicyPath = (p: string): p is PolicyPath => p in POLICY_PAGES;

export function Footer() {
  return (
    <footer className="site-footer">
      {Object.entries(POLICY_PAGES).map(([path, title]) => <a key={path} href={path}>{title}</a>)}
      <span className="muted">© 2026 {BUSINESS.name}</span>
    </footer>
  );
}

export function PolicyPage({ path }: { path: PolicyPath }) {
  return (
    <div className="page policy">
      <header className="header">
        <div>
          <a href="/" className="home-link"><h1>PrepRadar</h1></a>
          <p className="muted">Interview questions real candidates reported, by company.</p>
        </div>
      </header>
      <article>
        <h2>{POLICY_PAGES[path]}</h2>
        {path !== "/pricing" && path !== "/contact" && <p className="muted small">Last updated {BUSINESS.updated}</p>}
        {BODIES[path]()}
      </article>
      <Footer />
    </div>
  );
}

const Mail = () => <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a>;

function Pricing() {
  const { config } = useAccount();
  const price = priceLabel(config);
  return (
    <>
      <div className="plans">
        <section className="plan">
          <span className="pack-kicker">Free</span>
          <p className="plan-price">₹0</p>
          <ul>
            <li>Every company on the site</li>
            <li>Half of each category's questions, with the rest outlined</li>
            <li>Ask for a new company: 2 a day, 5 quick searches a day</li>
          </ul>
        </section>
        <section className="plan featured">
          <span className="pack-kicker">PrepRadar Pro</span>
          <p className="plan-price">{price || "Monthly plan"}</p>
          <ul>
            <li>Every question, for every company</li>
            <li>Every candidate story, with its round-by-round timeline</li>
            <li>The complete prep guide for each company</li>
            <li>Ask for a new company: 5 a day, 15 quick searches a day</li>
          </ul>
          <a className="primary button-link" href="/">Subscribe on the site</a>
        </section>
      </div>
      <p>
        Prices are in Indian rupees and include all charges. The plan renews every month through Razorpay (UPI AutoPay
        or card) until you cancel. Sign in with Google, open any company and press <b>Subscribe</b>; access starts as
        soon as the payment is confirmed. Cancel any time with <b>Cancel plan</b> at the top of the site. See{" "}
        <a href="/refunds">Cancellation &amp; Refunds</a>.
      </p>
    </>
  );
}

function Terms() {
  return (
    <>
      <p>
        PrepRadar ("we", "us") is run by {BUSINESS.name}, an individual based in India. By using
        prepradar.prepradar-worker.workers.dev ("the site") you agree to these terms. If you don't agree, please don't
        use the site.
      </p>
      <h3>What PrepRadar is</h3>
      <p>
        PrepRadar collects interview questions that candidates have reported in public write-ups of their own
        interviews, groups them by company, role and topic, and writes a prep guide from them. Questions are
        summarised in our own words. We are not affiliated with, endorsed by or sponsored by any company listed;
        company names and trademarks belong to their owners and are used only to say which interviews a question
        comes from.
      </p>
      <h3>No guarantee</h3>
      <p>
        Questions and guides come from what candidates reported and are organised with the help of AI. They may be
        incomplete, out of date or wrong, and a company may ask entirely different questions. The site is a study
        aid; we don't promise any interview result or job offer.
      </p>
      <h3>Accounts</h3>
      <p>
        You sign in with your Google account. Keep it secure; a subscription belongs to that account and works on any
        device signed in with it. You must be at least 18 years old, or have a parent's or guardian's permission, to
        subscribe.
      </p>
      <h3>Subscription and payment</h3>
      <p>
        PrepRadar Pro is a monthly subscription at the price shown on the <a href="/pricing">Pricing</a> page. Payments
        are processed by Razorpay; we never see your card or UPI details. The subscription renews automatically each
        month until you cancel. If a renewal fails, access ends at the end of the paid period. We may change the price
        for future months; we will say so on the site at least 7 days before a changed price applies to you, and you can
        cancel before then. Cancellation and refunds are covered in{" "}
        <a href="/refunds">Cancellation &amp; Refunds</a>.
      </p>
      <h3>Fair use</h3>
      <p>
        The paid content is for your own preparation. Please don't share your account, copy or resell the content, or
        scrape the site with automated tools. We may suspend an account that does, and limit how many new companies
        anyone can request each day.
      </p>
      <h3>Removal requests</h3>
      <p>
        If something on the site is yours and you want it removed, or names you, email <Mail /> with the page and we
        will remove it, usually within 3 business days.
      </p>
      <h3>Liability</h3>
      <p>
        The site is provided "as is". To the extent the law allows, our total liability to you for anything related to
        the site is limited to the amount you paid us in the 3 months before the claim.
      </p>
      <h3>Changes and law</h3>
      <p>
        We may update these terms; the date at the top shows the latest version, and continuing to use the site means
        you accept it. These terms are governed by the laws of India, and the courts of India have jurisdiction.
        Questions: <Mail />.
      </p>
    </>
  );
}

function Privacy() {
  return (
    <>
      <p>
        This policy explains what PrepRadar, run by {BUSINESS.name}, collects about you and why. In short: as little as
        possible, no ads, no tracking, and nothing sold.
      </p>
      <h3>What we collect</h3>
      <ul>
        <li>
          <b>Google sign-in.</b> Google tells us your account id, name, email address and profile picture. The name,
          email and picture are sent to your browser to show who is signed in; we store only your Google account id,
          as the key of your subscription record.
        </li>
        <li>
          <b>Subscription.</b> For subscribers we keep the Razorpay subscription id, its status and when the paid period
          ends. Payments happen on Razorpay; your card, UPI and bank details go to Razorpay only and never reach us.
          Razorpay's own privacy policy applies to them.
        </li>
        <li>
          <b>Daily counts.</b> To enforce the daily limits we count your requests per day; the counts are deleted after
          2 days.
        </li>
        <li>
          <b>Notifications</b>, only if you turn them on: your browser's push address, kept until the company you asked
          for is ready, and never longer than a week.
        </li>
        <li>
          <b>Server logs.</b> Our host, Cloudflare, records each request (IP address, page, time and browser) for a few
          days, which we use to fix errors and stop abuse.
        </li>
      </ul>
      <h3>What we don't do</h3>
      <p>
        We don't use advertising or analytics trackers, we don't set tracking cookies, and we don't sell or rent your
        data. Your browser stores your sign-in for up to 30 days so you stay signed in; signing out removes it. Google
        and Razorpay may set their own cookies when you use their sign-in or checkout.
      </p>
      <h3>Who else handles data</h3>
      <ul>
        <li>Cloudflare: hosts the site and stores the records above.</li>
        <li>Google: sign-in.</li>
        <li>Razorpay: payments and subscriptions.</li>
        <li>
          Tavily and Google Gemini: when you ask for a new company, its name is sent to them to find and read public
          interview write-ups. Nothing about you is sent with it.
        </li>
      </ul>
      <h3>Your choices</h3>
      <p>
        You can sign out at any time, and cancel a subscription with <b>Cancel plan</b>. To see or delete what we hold
        about you, email <Mail /> from the Google account you signed in with; we will reply within 30 days. Records
        needed for payment and tax rules are kept for as long as the law requires.
      </p>
      <h3>Changes</h3>
      <p>We will post any change here with a new date at the top.</p>
    </>
  );
}

function Refunds() {
  return (
    <>
      <h3>Cancelling</h3>
      <p>
        You can cancel PrepRadar Pro at any time: sign in and press <b>Cancel plan</b> at the top of the site, or email{" "}
        <Mail />. Cancelling stops all future renewals. You keep full access until the end of the month you have already
        paid for, and you are not charged again.
      </p>
      <h3>Refunds</h3>
      <p>
        Because access to all content starts the moment you subscribe, payments are not refundable, including for part
        of a month or a month you didn't use.
      </p>
      <p>
        The exceptions: if you were charged twice for the same period, charged after you cancelled, or charged but
        never got access, email <Mail /> within 30 days of the charge. We refund the full amount for such a charge to
        the original payment method; Razorpay and your bank usually take 5 to 7 business days to return it.
      </p>
    </>
  );
}

function Delivery() {
  return (
    <>
      <p>
        PrepRadar Pro is a digital service; nothing is shipped. Access starts immediately after Razorpay confirms your
        payment, on the Google account you subscribed with, on any device. You'll see <b>PRO</b> next to your name at the
        top of the site.
      </p>
      <p>
        If you paid and don't see access within an hour, sign out and back in. If it still doesn't show, email{" "}
        <Mail /> with the payment id from Razorpay's receipt and we will fix it or refund the charge
        (see <a href="/refunds">Cancellation &amp; Refunds</a>).
      </p>
    </>
  );
}

function Contact() {
  return (
    <>
      <p>For questions about the site, your subscription, a payment or a removal request:</p>
      <dl className="contact">
        <dt>Run by</dt><dd>{BUSINESS.name}</dd>
        <dt>Email</dt><dd><Mail /></dd>
        {BUSINESS.address && (<><dt>Address</dt><dd>{BUSINESS.address}</dd></>)}
      </dl>
      <p className="muted">We reply within 2 business days.</p>
    </>
  );
}

const BODIES: Record<PolicyPath, () => ReactNode> = {
  "/pricing": Pricing,
  "/terms": Terms,
  "/privacy": Privacy,
  "/refunds": Refunds,
  "/delivery": Delivery,
  "/contact": Contact,
};
