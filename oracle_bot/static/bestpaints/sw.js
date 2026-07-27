const CACHE = "bp-survey-v23";
const ASSETS = [
  "./",
  "./index.html",
  "./css/styles.css",
  "./js/app.js",
  "./js/calc.js",
  "./js/storage.js",
  "./js/house3d.js",
  "./js/report.js",
  "./js/quality.js",
  "./js/share.js",
  "./js/photos.js",
  "./js/keypad.js",
  "./js/scale.js",
  "./js/trash.js,
  "./js/crm.js"",
  "./data/catalog.json",
  "./data/tech-matrix.js",
  "./data/extras.js",
  "./data/objects.js",
  "./data/tips.js",
  "./data/pitfalls.js",
  "./data/lessons.js",
  "./manifest.webmanifest",
  "./assets/icon.svg",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  e.respondWith(
    caches.match(req).then((cached) =>
      cached ||
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() => cached)
    )
  );
});
