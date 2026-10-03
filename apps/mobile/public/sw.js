const CACHE_NAME = 'cocoon-offline-v1';
const OFFLINE_FILES = ['/offline.html', '/icons/icon-192.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(OFFLINE_FILES)));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((name) => name.startsWith('cocoon-offline-') && name !== CACHE_NAME)
            .map((name) => caches.delete(name)),
        ),
      ),
  );
});

self.addEventListener('fetch', (event) => {
  if (
    event.request.mode !== 'navigate' ||
    new URL(event.request.url).origin !== self.location.origin
  ) {
    return;
  }
  event.respondWith(fetch(event.request).catch(() => caches.match('/offline.html')));
});

self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data?.json() ?? {};
  } catch {
    // The service worker still shows the generic notification for malformed data.
  }
  event.waitUntil(
    self.registration.showNotification(payload.title || 'Cocoon', {
      body: payload.body || 'Votre assistant a du nouveau pour vous.',
      icon: '/icons/icon-192.png',
      data: { url: '/home' },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
      const existing = windows.find((windowClient) =>
        windowClient.url.startsWith(self.location.origin),
      );
      return existing ? existing.focus() : clients.openWindow('/home');
    }),
  );
});
