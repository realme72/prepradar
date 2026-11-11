// Buying a pack: the Worker creates a Razorpay order at the catalog price, Razorpay's
// own checkout takes the payment, and the Worker verifies it before handing back an
// access token. Card/UPI details only ever go to Razorpay, never to our code.
import { postJson } from "./api";
import { saveToken } from "./access";

type Order = { order_id: string; amount: number; currency: string; key_id: string; title: string };
type Granted = { pack: string; title: string; token: string };
type RazorpayResponse = { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string };

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

export async function buyPack(pack: string): Promise<Granted> {
  const [order] = await Promise.all([postJson<Order>("/api/checkout", { pack }), loadCheckout()]);
  const granted = await new Promise<Granted>((resolve, reject) => {
    let lastError = "";
    const rzp = new window.Razorpay!({
      key: order.key_id,
      order_id: order.order_id,
      amount: order.amount,
      currency: order.currency,
      name: "PrepRadar",
      description: order.title,
      theme: { color: "#00c8d7" },
      handler: (r: RazorpayResponse) =>
        postJson<Granted>("/api/verify", { order_id: r.razorpay_order_id, payment_id: r.razorpay_payment_id,
                                           signature: r.razorpay_signature }).then(resolve, reject),
      // Closing the window ends the attempt; a failed card inside it can be retried there.
      modal: { ondismiss: () => reject(lastError ? new Error(lastError) : new Cancelled("Payment cancelled")) },
    });
    rzp.on("payment.failed", (r) => (lastError = r.error.description));
    rzp.open();
  });
  saveToken(granted.pack, granted.token);
  return granted;
}

export async function recoverPack(paymentId: string): Promise<Granted> {
  const granted = await postJson<Granted>("/api/recover", { payment_id: paymentId });
  saveToken(granted.pack, granted.token);
  return granted;
}
