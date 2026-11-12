import { postJson, type CompanyRequest } from "./api";

// "Notify me when it's ready": a browser notification once a requested company's full
// collection finishes, even with the site closed. The Worker sends it (worker/src/push.ts);
// public/sw.js shows it.

// iPhones and iPads only support this for a site added to the Home Screen.
export const canNotify = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

// The key arrives base64url-encoded; the browser wants its bytes.
function keyBytes(b64url: string) {
  const b64 = b64url.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(b64url.length / 4) * 4, "=");
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

export async function notifyWhenReady(company: string, pushKey: string) {
  const permission = await Notification.requestPermission();
  if (permission === "denied") throw new Error("Notifications are blocked for this site; allow them in the browser's site settings.");
  if (permission !== "granted") throw new Error("Notifications weren't allowed.");
  await navigator.serviceWorker.register("/sw.js");
  const reg = await navigator.serviceWorker.ready;
  const sub = (await reg.pushManager.getSubscription())
    ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(pushKey) }));
  return postJson<CompanyRequest & { watching?: boolean }>("/api/notify", { company, endpoint: sub.endpoint });
}
