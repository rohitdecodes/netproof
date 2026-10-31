"use strict";
// NetProof static replay: answers the dashboard's /api calls from exported JSON files.
// Loaded before app.js on the hosted site only; the local dashboard never loads it.
(function () {
  const realFetch = window.fetch.bind(window);
  const DATA = "data/";
  const json = (obj, status = 200) =>
    new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });
  const file = (path) => realFetch(DATA + path);
  window.NETPROOF_REPLAY = true;

  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : input.url;
    if (!url.startsWith("/api/")) return realFetch(input, init);
    const method = ((init && init.method) || "GET").toUpperCase();
    if (method !== "GET") {
      return new Response("This is a read-only replay of recorded runs. Clone the repository to run the lab yourself.",
                          { status: 403 });
    }
    const u = new URL(url, "http://replay.invalid");
    const p = u.pathname, q = u.searchParams;
    if (p === "/api/status") return json({ active: null });
    if (p === "/api/topology") return file("topology.json");
    if (p === "/api/profiles") return file("profiles.json");
    if (p === "/api/labels") return file("labels.json");
    if (p === "/api/runs") return file("runs.json");
    if (p === "/api/catalog") return file(`catalog-${q.get("split") || "dev"}.json`);
    if (p === "/api/scoreboard") {
      return file(q.get("label") ? `scoreboard/${encodeURIComponent(q.get("label"))}.json` : "scoreboard/_all.json");
    }
    let m = p.match(/^\/api\/runs\/([^/]+)\/events$/);
    if (m) {
      const r = await file(`events/${m[1]}.json`);
      if (!r.ok) return r;
      const after = Number(q.get("after") || 0);
      return json((await r.json()).filter((e) => e.seq > after));
    }
    m = p.match(/^\/api\/runs\/([^/]+)$/);
    if (m) return json({ run: null, active: false });
    return new Response("Not part of this replay.", { status: 404 });
  };

  document.addEventListener("DOMContentLoaded", () => {
    document.body.classList.add("replay");
    document.querySelectorAll("button.featured[data-run]").forEach((b) => {
      b.addEventListener("click", () => window.openRun && window.openRun(b.dataset.run));
    });
  });
})();
