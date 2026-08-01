const CACHE = "bp-survey-v50";
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
  "./js/trash.js",
  "./js/crm.js",
  "./js/drawings.js",
  "./js/reports.js",
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
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (e) => {
  if (e.data && e.data.type === "SKIP_WAITING") self.skipWaiting();
});

function shouldBypassCache(url) {
  const path = url.pathname || "";
  if (path.includes("/api/")) return true;
  if (path.includes("/docs/")) return true;
  if (/\.pdf$/i.test(path)) return true;
  if (path.endsWith("/login") || path.endsWith("/logout")) return true;
  if (path.endsWith("/sw.js")) return true;
  if (path.endsWith("/index.html") || path.endsWith("/cabinet.html")) return true;
  if (path.endsWith("/bestpaints") || path.endsWith("/bestpaints/")) return true;
  return false;
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  let url;
  try {
    url = new URL(req.url);
  } catch (err) {
    return;
  }
  if (url.origin !== self.location.origin) return;

  if (shouldBypassCache(url)) {
    e.respondWith(fetch(req, { cache: "no-store" }).catch(() => caches.match(req)));
    return;
  }

  // network-first: всегда тянем свежее, кэш только как офлайн-запас
  e.respondWith(
    fetch(req, { cache: "no-cache" })
      .then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req))
  );
});
