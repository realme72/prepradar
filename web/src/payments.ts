// Subscribing: the Worker creates a Razorpay subscription for the signed-in user,
// Razorpay's own checkout takes the first payment and sets up UPI AutoPay or card
// renewals, and the Worker verifies it. Card/UPI details only ever go to Razorpay.
import { postJson } from "./api";
import type { Session } from "./auth";

type Started = { subscription_id: string; key_id: string };
type RazorpayResponse = { razorpay_payment_id: string; razorpay_subscription_id: string; razorpay_signature: string };
export type Me = { access: boolean; status: string | null; current_end: number | null; cancel_at_end: boolean };

declare global {
  interface Window {
    Razorpay?: new (options: object) => { open(): void; on(event: string, cb: (r: { error: { description: string } }) => void): void };
  }
}

function loadCheckout(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Couldn't load Razorpay checkout. Check your connection and try again."));
    document.head.appendChild(s);
  });
}

export class Cancelled extends Error {}

export async function subscribe(session: Session): Promise<Me> {
  const [started] = await Promise.all([postJson<Started>("/api/subscribe", {}), loadCheckout()]);
  return new Promise<Me>((resolve, reject) => {
    let lastError = "";
    const rzp = new window.Razorpay!({
      key: started.key_id,
      subscription_id: started.subscription_id,
      name: "PrepRadar",
      description: "Every company, every question · monthly",
      prefill: { name: session.name, email: session.email }, // typed for them, sent only to Razorpay
      theme: { color: "#00c8d7" },
      handler: (r: RazorpayResponse) =>
        postJson<Me>("/api/subscription/verify", { payment_id: r.razorpay_payment_id,
                                                   subscription_id: r.razorpay_subscription_id,
                                                   signature: r.razorpay_signature }).then(resolve, reject),
      // Closing the window ends the attempt; a failed payment inside it can be retried there.
      modal: { ondismiss: () => reject(lastError ? new Error(lastError) : new Cancelled("Payment cancelled")) },
    });
    rzp.on("payment.failed", (r) => (lastError = r.error.description));
    rzp.open();
  });
}

export const cancelSubscription = () => postJson<Me>("/api/subscription/cancel", {});
