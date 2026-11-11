// The three Razorpay calls the Worker needs, authenticated with the account's key pair.
// https://razorpay.com/docs/api/orders/ and /payments/

export type Order = { id: string; amount: number; currency: string; notes?: Record<string, string> };
export type Payment = { id: string; order_id: string; amount: number; currency: string; status: string };

export class HttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Fields are written out rather than as `constructor(private keyId…)`: Node runs the
// tests by stripping types, which can't handle that shorthand.
export class Razorpay {
  private keyId: string;
  private keySecret: string;
  constructor(keyId: string, keySecret: string) {
    this.keyId = keyId;
    this.keySecret = keySecret;
  }

  private async call<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(`https://api.razorpay.com/v1${path}`, {
      method: body ? "POST" : "GET",
      headers: { Authorization: `Basic ${btoa(`${this.keyId}:${this.keySecret}`)}`, "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 400 || res.status === 404) throw new HttpError(404, "Payment not found");
    if (!res.ok) throw new HttpError(502, `Razorpay returned ${res.status}`);
    return res.json() as Promise<T>;
  }

  createOrder(amount: number, receipt: string, notes: Record<string, string>) {
    return this.call<Order>("/orders", { amount, currency: "INR", receipt, notes });
  }

  payment(id: string) {
    return this.call<Payment>(`/payments/${id}`);
  }

  order(id: string) {
    return this.call<Order>(`/orders/${id}`);
  }

  // Accounts with manual capture leave payments "authorized"; capturing takes the money.
  capture(p: Payment) {
    return this.call<Payment>(`/payments/${p.id}/capture`, { amount: p.amount, currency: p.currency });
  }
}
