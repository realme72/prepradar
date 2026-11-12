// PrepRadar's service worker: it only shows notifications ("amazon is ready").
// Pushes arrive empty (see worker/src/push.ts); the message waits on the server and is
// fetched here, with this browser's subscription as the key.
self.addEventListener("push", (event) => {
  event.waitUntil((async () => {
    const sub = await self.registration.pushManager.getSubscription();
    let notices = [];
    try {
      const res = await fetch("/api/notify/pending", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: sub && sub.endpoint }),
      });
      if (res.ok) notices = await res.json();
    } catch {
      // offline: fall through to the generic notice
    }
    // browsers require a visible notification for every push
    if (!notices.length) notices = [{ title: "PrepRadar", body: "A company you asked for has an update.", url: "/" }];
    await Promise.all(notices.map((n) =>
      self.registration.showNotification(n.title, { body: n.body, icon: "/apple-touch-icon.png", tag: n.url, data: { url: n.url } })));
  })());
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow((event.notification.data && event.notification.data.url) || "/"));
});
