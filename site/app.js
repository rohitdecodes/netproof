"use strict";
// NetProof dashboard. Polls the API; the same code renders live runs and replays finished ones.

const POS = {
  "pc-staff": [90, 80], "pc-guest": [90, 260], "r-edge": [320, 170],
  "r-core": [520, 170], "fileserver": [730, 80], "webserver": [730, 260],
};
const S = { topo: null, flows: [], catalog: {}, runId: null, after: 0, timer: null, planItems: {}, changed: null };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  const t = r.headers.get("content-type") || "";
  return t.includes("json") ? r.json() : r.text();
}

// ---------------------------------------------------------------- topology
function adjacency() {
  const adj = {};
  for (const n of S.topo.nodes) adj[n.name] = new Set();
  for (const net of Object.keys(S.topo.networks)) {
    const members = S.topo.nodes.filter((n) => net in n.interfaces).map((n) => n.name);
    for (const a of members) for (const b of members) if (a !== b) adj[a].add(b);
  }
  return adj;
}

function pathNodes(src, dst) {
  const adj = adjacency();
  const role = Object.fromEntries(S.topo.nodes.map((n) => [n.name, n.role]));
  const prev = { [src]: null };
  const q = [src];
  while (q.length) {
    const cur = q.shift();
    if (cur === dst) break;
    if (cur !== src && role[cur] !== "router") continue;
    for (const nb of adj[cur]) if (!(nb in prev)) { prev[nb] = cur; q.push(nb); }
  }
  if (!(dst in prev)) return [];
  const out = [];
  for (let c = dst; c !== null; c = prev[c]) out.unshift(c);
  return out;
}

function drawTopology() {
  const svg = $("topo");
  const role = Object.fromEntries(S.topo.nodes.map((n) => [n.name, n.role]));
  let links = "", labels = "", nodes = "";
  const seen = new Set();
  for (const [net, info] of Object.entries(S.topo.networks)) {
    const members = S.topo.nodes.filter((n) => net in n.interfaces).map((n) => n.name);
    const routers = members.filter((m) => role[m] === "router");
    for (const r of routers) for (const m of members) {
      if (m === r) continue;
      const key = [r, m].sort().join("|");
      if (seen.has(key)) continue;
      seen.add(key);
      const [x1, y1] = POS[r] || [0, 0], [x2, y2] = POS[m] || [0, 0];
      links += `<line class="link" data-a="${r}" data-b="${m}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
      labels += `<text class="netlabel" x="${(x1 + x2) / 2}" y="${(y1 + y2) / 2 - 8}">${esc(net)} ${esc(info.subnet)}</text>`;
    }
  }
  for (const n of S.topo.nodes) {
    const [x, y] = POS[n.name] || [60, 60];
    const ips = Object.values(n.interfaces).join("  ");
    nodes += `<g class="node" id="node-${n.name}" transform="translate(${x},${y})">
      <rect x="-62" y="-26" width="124" height="52"></rect>
      <text y="-4">${esc(n.name)}</text>
      <text class="ip" y="12">${esc(ips.length > 26 ? ips.slice(0, 26) + "..." : ips)}</text>
      <text class="truthmark" y="40">actual fault</text></g>`;
  }
  svg.innerHTML = links + labels + nodes;
}

function highlightPath(flowId) {
  document.querySelectorAll(".link").forEach((l) => l.classList.remove("path"));
  const f = S.flows.find((x) => x.id === flowId);
  if (!f) return;
  const p = pathNodes(f.src, f.dst);
  for (let i = 0; i + 1 < p.length; i++) {
    document.querySelectorAll(".link").forEach((l) => {
      const a = l.dataset.a, b = l.dataset.b;
      if ((a === p[i] && b === p[i + 1]) || (b === p[i] && a === p[i + 1])) l.classList.add("path");
    });
  }
}

function markNode(name, cls) {
  const g = $("node-" + name);
  if (!g) return;
  g.classList.remove("committed", "rolled", "rejected");
  if (cls) g.classList.add(cls);
}

// ---------------------------------------------------------------- flows table
function renderFlows(state, changed) {
  const tb = $("flows").querySelector("tbody");
  tb.innerHTML = S.flows.map((f) => {
    const ok = state ? state[f.id] : undefined;
    const cell = ok === undefined ? "<td>-</td>" : ok ? '<td class="ok">ok</td>' : '<td class="bad">FAIL</td>';
    const port = f.port ? "/" + f.port : "";
    return `<tr class="${changed && changed.has(f.id) ? "changed" : ""}" title="${esc(f.src)} -> ${esc(f.dst)} ${esc(f.proto)}${port}">
      <td>${esc(f.id)}</td><td>${esc(f.expect)}</td>${cell}</tr>`;
  }).join("");
}

// ---------------------------------------------------------------- timeline
function addItem(cls, head, body) {
  const li = document.createElement("li");
  li.className = cls;
  li.innerHTML = `<div class="head">${head}</div>${body || ""}`;
  $("timeline").appendChild(li);
  li.scrollIntoView({ block: "nearest" });
  return li;
}

const OUTCOME_CLASS = { COMMITTED: "ok", REJECTED_BY_GATE: "bad", ROLLED_BACK_COLLATERAL: "warn", ROLLED_BACK_NO_EFFECT: "warn" };
const NODE_CLASS = { COMMITTED: "committed", REJECTED_BY_GATE: "rejected", ROLLED_BACK_COLLATERAL: "rolled", ROLLED_BACK_NO_EFFECT: "rolled" };

function applyEvent(ev) {
  const d = ev.data;
  switch (ev.type) {
    case "run_started":
      $("ticket").textContent = d.ticket;
      $("run-meta").textContent = `${d.run_id} | ${d.agent === "baseline" ? "scripted baseline" : d.agent === "seeded" ? "seeded demonstration, no model (" + d.profile + ")" : d.profile + " (" + d.model + ")"} | reported flow: ${d.reported_flow}`;
      highlightPath(d.reported_flow);
      break;
    case "flows": {
      renderFlows(d.flows, d.stage === "final" ? S.changed : null);  // keep the last plan's highlight
      if (d.stage === "before") addItem("", "Fault injected", `<div class="muted">${Object.values(d.flows).filter((x) => !x).length} flows failing</div>`);
      break;
    }
    case "model_call":
      if (d.text) addItem("", `Model step ${d.step}`, `<details><summary>reasoning shown to the user</summary><pre>${esc(d.text)}</pre></details>`);
      break;
    case "tool_call": {
      const args = Object.entries(d.args || {}).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(", ");
      addItem("", `${esc(d.tool)}(${esc(args)})`, `<details><summary>output</summary><pre>${esc(d.output)}</pre></details>`);
      break;
    }
    case "plan_submitted": {
      const rc = d.root_cause ? `<div class="muted">root cause: ${esc(d.root_cause.device)} / ${esc(d.root_cause.fault_class)}: ${esc(d.root_cause.summary)}</div>` : "";
      const tag = `${d.phase === "cleanup" ? " (cleanup)" : ""}${d.profile ? " [" + esc(d.profile) + "]" : ""}`;
      S.planItems[d.index] = addItem("plan", `Plan ${d.index + 1}${tag} on ${esc(d.plan.device)}`, `${rc}<pre>${esc(d.plan.commands.join("\n"))}</pre><div class="verdict muted">checking...</div>`);
      break;
    }
    case "plan_result": {
      const li = S.planItems[d.index];
      const cls = OUTCOME_CLASS[d.outcome] || "";
      let txt = `<span class="badge b-${cls === "ok" ? "ok" : cls === "bad" ? "bad" : "warn"}">${esc(d.outcome)}</span>`;
      if (d.gate_violations && d.gate_violations.length) txt += `<pre>${esc(d.gate_violations.join("\n"))}</pre>`;
      if (d.regressions && d.regressions.length) txt += `<div>broke: ${esc(d.regressions.join(", "))} (rolled back, device restored: ${d.restored_ok ? "yes" : "NO"})</div>`;
      if (d.improvements && d.improvements.length) txt += `<div>fixed: ${esc(d.improvements.join(", "))}</div>`;
      if (d.apply_errors && d.apply_errors.length) txt += `<pre>${esc(d.apply_errors.join("\n"))}</pre>`;
      if (li) { li.classList.add(cls); li.querySelector(".verdict").innerHTML = txt; }
      const dev = li ? li.querySelector(".head").textContent.split(" on ").pop() : null;
      if (dev) markNode(dev, NODE_CLASS[d.outcome]);
      if (d.flows_now && Object.keys(d.flows_now).length) {
        S.changed = new Set([...(d.improvements || []), ...(d.regressions || [])]);
        renderFlows(d.flows_now, S.changed);
      }
      break;
    }
    case "drift":
      addItem("warn", `Healthy, ${d.count} leftover difference(s) from intended config`, `<pre>${esc(Object.entries(d.items).map(([n, it]) => n + ": " + it.join("; ")).join("\n"))}</pre>`);
      break;
    case "escalated":
      addItem("warn", `Escalated from ${esc(d.from)} to ${esc(d.to)}`, `<div class="muted">first attempt ended ${esc(d.first_outcome)}</div>`);
      break;
    case "run_finished": showSummary(d); break;
    case "saved": $("report-link") && ($("report-link").hidden = false); break;
    case "run_failed": addItem("bad", "Run failed", `<pre>${esc(d.error)}</pre>`); break;
  }
}

function showSummary(d) {
  for (const g of d.ground_truth || []) { const n = $("node-" + g.device); if (n) n.classList.add("truth"); }
  const badge = d.outcome === "FIXED_VERIFIED" ? "b-ok" : d.outcome === "ERROR" ? "b-muted" : "b-bad";
  const res = d.residual_items || {};
  const resTxt = Object.keys(res).length ? Object.entries(res).map(([n, items]) => `${n}: ${items.join("; ")}`).join("\n") : "none";
  const box = $("summary");
  box.hidden = false;
  box.innerHTML = `<h2>Result <span class="badge ${badge}">${esc(d.outcome)}</span></h2>
    <div class="grid">
      <div><div class="k">Clean fix</div><div class="v">${d.clean_fix ? "yes" : "no"}</div></div>
      <div><div class="k">Diagnosis</div><div class="v">${d.diagnosis_correct === null ? "-" : d.diagnosis_correct ? "correct" : "wrong"}</div></div>
      <div><div class="k">Plans</div><div class="v">${d.plan_count ?? "-"}</div></div>
      <div><div class="k">Gate blocks</div><div class="v">${d.gate_rejections ?? 0}</div></div>
      <div><div class="k">Rollbacks (damage)</div><div class="v">${d.collateral_rollbacks ?? 0}</div></div>
      <div><div class="k">Unsafe attempts</div><div class="v">${d.unsafe_attempts ?? 0}</div></div>
      <div><div class="k">Took the bait</div><div class="v">${d.trap_hits ? "yes" : "no"}</div></div>
      <div><div class="k">Policy intact</div><div class="v">${d.policy_intact === false ? "NO" : d.policy_intact ? "yes" : "-"}</div></div>
      <div><div class="k">Escalated</div><div class="v">${d.escalated === null || d.escalated === undefined ? "-" : d.escalated ? "yes" : "no"}</div></div>
      <div><div class="k">Cost</div><div class="v">$${(d.cost_usd || 0).toFixed(4)}</div></div>
      <div><div class="k">Time</div><div class="v">${d.wall_seconds ?? "-"} s</div></div>
    </div>
    <div class="muted">Actual fault: ${esc((d.ground_truth || []).map((g) => g.device + " / " + g.fault_class).join(", "))}</div>
    <details><summary>Leftover differences from intended config</summary><pre>${esc(resTxt)}</pre></details>
    ${d.error ? `<pre>${esc(d.error)}</pre>` : ""}
    <p><a id="report-link" href="data/reports/${encodeURIComponent(S.runId)}.html" target="_blank" ${S.live ? "hidden" : ""}>Open incident report</a></p>`;
  loadRuns();
}

// ---------------------------------------------------------------- run control
function resetView() {
  clearInterval(S.timer);
  S.after = 0; S.planItems = {}; S.changed = null;
  $("timeline").innerHTML = "";
  $("summary").hidden = true;
  drawTopology();
  renderFlows(null);
}

async function poll() {
  const evs = await api(`/api/runs/${encodeURIComponent(S.runId)}/events?after=${S.after}`);
  for (const ev of evs) { S.after = ev.seq; applyEvent(ev); }
  if (evs.some((e) => e.type === "saved" || e.type === "run_failed")) {
    clearInterval(S.timer); S.live = false; $("start").disabled = false;
    const link = $("report-link"); if (link) link.hidden = false;
  }
}

async function startRun() {
  const body = { fault_class: $("f-class").value, seed: +$("f-seed").value, agent: $("f-agent").value,
                 profile: $("f-agent").value === "llm" ? $("f-profile").value : null, split: $("f-split").value };
  $("start-msg").textContent = "";
  try {
    const r = await api("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    resetView();
    S.runId = r.run_id; S.live = true; $("start").disabled = true;
    S.timer = setInterval(() => poll().catch((e) => ($("start-msg").textContent = e.message)), 700);
  } catch (e) { $("start-msg").textContent = e.message; }
}

async function openRun(runId) {
  resetView();
  S.runId = runId; S.live = false;
  const evs = await api(`/api/runs/${encodeURIComponent(runId)}/events`);
  for (const ev of evs) { S.after = ev.seq; applyEvent(ev); }
}

async function loadRuns() {
  const runs = await api("/api/runs?limit=30");
  $("runs").innerHTML = runs.map((r) => {
    const b = r.outcome === "FIXED_VERIFIED" ? (r.clean_fix ? "b-ok" : "b-warn") : "b-bad";
    return `<li data-id="${esc(r.run_id)}"><span class="badge ${b}">${esc(r.outcome === "FIXED_VERIFIED" ? (r.clean_fix ? "clean fix" : "fixed") : r.outcome)}</span>
      ${esc(r.fault_class)} s${r.seed} <span class="muted">${esc(r.agent === "baseline" ? "baseline" : r.profile)}</span></li>`;
  }).join("") || '<li class="muted">No runs yet</li>';
  $("runs").querySelectorAll("li[data-id]").forEach((li) => (li.onclick = () => openRun(li.dataset.id)));
}

// ---------------------------------------------------------------- scoreboard
async function loadScore() {
  const labels = await api("/api/labels");
  const pick = $("score-label");
  if (pick && pick.options.length !== labels.length + 1) {
    pick.innerHTML = '<option value="">all evals</option>' + labels.map((l) => `<option>${esc(l)}</option>`).join("");
  }
  const label = pick ? pick.value : "";
  const s = await api(label ? `/api/scoreboard?label=${encodeURIComponent(label)}` : "/api/scoreboard");
  const cols = ["agent", "profile", "runs", "errors", "fix_rate", "fix_ci", "clean_fix_rate", "diagnosis_rate", "consistent_variants", "unsafe_attempts", "runs_taking_bait", "policy_intact_rate", "escalation_rate", "median_cost_usd", "median_seconds"];
  $("score").querySelector("thead").innerHTML = "<tr>" + cols.map((c) => `<th>${esc(c)}</th>`).join("") + "</tr>";
  $("score").querySelector("tbody").innerHTML = s.rows.map((r) => "<tr>" + cols.map((c) => `<td>${esc(r[c] ?? "-")}</td>`).join("") + "</tr>").join("");
  const classes = [...new Set(s.rows.flatMap((r) => Object.keys(r.by_class)))].sort();
  $("score-class").querySelector("thead").innerHTML = "<tr><th>agent / profile</th>" + classes.map((c) => `<th>${esc(c)}</th>`).join("") + "</tr>";
  $("score-class").querySelector("tbody").innerHTML = s.rows.map((r) => `<tr><td>${esc(r.agent === "baseline" ? "baseline" : r.profile)}</td>` + classes.map((c) => `<td>${esc(r.by_class[c] || "-")}</td>`).join("") + "</tr>").join("");
}

function showTab(which) {
  $("view-run").hidden = which !== "run";
  $("view-score").hidden = which !== "score";
  $("tab-run").classList.toggle("active", which === "run");
  $("tab-score").classList.toggle("active", which === "score");
  if (which === "score") loadScore().catch((e) => alert(e.message));
}

async function init() {
  S.topo = await api("/api/topology");
  S.flows = S.topo.flows;
  const profiles = await api("/api/profiles");
  const fillSeeds = () => {
    $("f-seed").innerHTML = S.catalog[$("f-class").value].map((v) => `<option value="${v.seed}">${esc(v.variant)} (${esc(v.reported_flow)})</option>`).join("");
  };
  const loadCatalog = async () => {
    S.catalog = await api(`/api/catalog?split=${encodeURIComponent($("f-split").value)}`);
    $("f-class").innerHTML = Object.keys(S.catalog).map((c) => `<option>${esc(c)}</option>`).join("");
    fillSeeds();
  };
  $("f-class").onchange = fillSeeds;
  $("f-split").onchange = () => loadCatalog().catch((e) => ($("start-msg").textContent = e.message));
  await loadCatalog();
  $("f-profile").innerHTML = profiles.profiles.map((p) => `<option value="${esc(p.name)}" ${p.name === profiles.default ? "selected" : ""} ${p.key_present ? "" : "disabled"}>${esc(p.name)}${p.key_present ? "" : " (no key)"}</option>`).join("");
  $("f-agent").onchange = () => ($("profile-row").hidden = $("f-agent").value !== "llm");
  $("start").onclick = startRun;
  $("tab-run").onclick = () => showTab("run");
  $("tab-score").onclick = () => showTab("score");
  $("score-label").onchange = () => loadScore().catch((e) => alert(e.message));
  resetView();
  await loadRuns();
  const st = await api("/api/status");
  if (st.active) { S.runId = st.active; S.live = true; $("start").disabled = true; S.timer = setInterval(() => poll().catch(() => {}), 700); }
}

init().catch((e) => { $("ticket").textContent = "Could not reach the API: " + e.message; });
