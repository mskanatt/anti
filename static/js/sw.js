// Service worker: Web Push уведомления + офлайн-доступ к оболочке приложения.
// Аудио здесь не обрабатывается — вся логика распознавания живёт во вкладке (device-listener.js).

const CACHE = "ab-shell-v1";
const SHELL = ["/", "/dashboard", "/device", "/static/css/style.css", "/static/js/api.js"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/events") || url.pathname.startsWith("/devices") || url.pathname.startsWith("/auth")) {
    return; // API-запросы никогда не кэшируем
  }
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});

self.addEventListener("push", (event) => {
  let data = { title: "⚠️ Anti-Bullying System", body: "Новое событие" };
  try { data = event.data.json(); } catch (_) {}
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      tag: data.tag || "ab-alert",
      icon: "/static/icons/icon-192.png",
      badge: "/static/icons/icon-192.png",
      data: { eventId: data.event_id },
      requireInteraction: true,
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window" }).then((clients) => {
      for (const c of clients) if (c.url.includes("/dashboard")) return c.focus();
      return self.clients.openWindow("/dashboard");
    })
  );
});