var CACHE = "yabot-mind-v1";
var PRECACHE = [
  "/",
  "/index.html",
  "/styles.css",
  "/mind.js",
  "/manifest.webmanifest",
  "/favicon.svg",
  "/favicon.png",
  "/favicon-32.png",
  "/apple-touch-icon.png",
  "/ya-crown.png",
  "/trueblast/",
  "/trueblast/index.html",
  "/trueblast/log.json",
  "/404.html"
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(PRECACHE.map(function (u) {
        return new Request(u, { cache: "reload" });
      })).catch(function () { /* partial ok */ });
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  var req = event.request;
  if (req.method !== "GET") return;
  event.respondWith(
    caches.match(req).then(function (hit) {
      if (hit) return hit;
      return fetch(req).then(function (res) {
        if (res && res.ok && (req.url.indexOf(self.location.origin) === 0)) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(req, copy); });
        }
        return res;
      }).catch(function () {
        if (req.mode === "navigate") return caches.match("/index.html");
        return new Response("", { status: 503, statusText: "Offline" });
      });
    })
  );
});
