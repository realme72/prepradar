// The Razorpay calls the Worker needs, authenticated with the account's key pair.
// https://razorpay.com/docs/api/payments/subscriptions/

export type Subscription = {
  id: string;
  status: string; // created | authenticated | active | pending | halted | cancelled | completed | expired
  current_end: number | null; // end of the paid period (unix seconds)
  notes?: Record<string, string>;
  has_scheduled_changes?: boolean;
};
export type Plan = { id: string; period: string; item: { amount: number; currency: string } };

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
    if (res.status === 400 || res.status === 404) throw new HttpError(404, "Not found at Razorpay");
    if (!res.ok) throw new HttpError(502, `Razorpay returned ${res.status}`);
    return res.json() as Promise<T>;
  }

  plan(id: string) {
    return this.call<Plan>(`/plans/${id}`);
  }

  // total_count is required; 120 monthly charges = 10 years, i.e. "until cancelled".
  createSubscription(planId: string, user: string) {
    return this.call<Subscription>("/subscriptions", { plan_id: planId, total_count: 120, customer_notify: 1,
                                                       notes: { user } });
  }

  subscription(id: string) {
    return this.call<Subscription>(`/subscriptions/${id}`);
  }

  // At cycle end: the subscriber keeps what they paid for until current_end.
  cancelAtCycleEnd(id: string) {
    return this.call<Subscription>(`/subscriptions/${id}/cancel`, { cancel_at_cycle_end: 1 });
  }
}
