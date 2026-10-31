"use strict";
// NetProof dashboard. Polls the API; the same code renders live runs and plays back finished ones.

const POS = {
  "pc-staff": [90, 80], "pc-guest": [90, 260], "r-edge": [320, 170],
  "r-core": [520, 170], "fileserver": [730, 80], "webserver": [730, 260],
};
const S = { topo: null, flows: [], catalog: {}, runId: null, after: 0, timer: null, planItems: {}, changed: null,
            live: false, queue: [], qi: 0, playing: false, playTimer: null, speed: 2, scoreToken: 0 };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  const t = r.headers.get("content-type") || "";
  return t.includes("json") ? r.json() : r.text();
}

// ---------------------------------------------------------------- names
const PROFILE_NAMES = { "spark-1.3": "Muse Spark 1.3", "spark-1.2": "Muse Spark 1.2", "spark-open": "Muse Spark Open",
                        "router": "Open-first router", "glimmer": "Muse Glimmer" };
function whoName(agent, profile) {
  if (agent === "baseline") return "Scripted runbook";
  if (agent === "seeded") return "Seeded demo, no model";
  if (agent === "router" || profile === "router") return "Open-first router";
  return PROFILE_NAMES[profile] || profile || agent || "-";
}
const OUTCOME_TEXT = { FIXED_VERIFIED: "Fixed and verified", ROLLED_BACK_COLLATERAL: "Rolled back", REJECTED_BY_GATE: "Refused by the gate",
                       ROLLED_BACK_NO_EFFECT: "Not fixed", BUDGET_EXHAUSTED: "Not fixed (budget used up)", ERROR: "Infrastructure error" };
const flowById = (id) => S.flows.find((f) => f.id === id);
const flowPath = (f) => f ? `${f.src} → ${f.dst} ${f.proto}${f.port ? "/" + f.port : ""}` : "";

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
      labels += `<text class="netlabel" x="${(x1 + x2) / 2}" y="${(y1 + y2) / 2 - 9}">${esc(net)} ${esc(info.subnet)}</text>`;
    }
  }
  for (const n of S.topo.nodes) {
    const [x, y] = POS[n.name] || [60, 60];
    const ips = Object.values(n.interfaces).join("  ");
    nodes += `<g class="node" id="node-${n.name}" transform="translate(${x},${y})">
      <rect x="-64" y="-27" width="128" height="54"></rect>
      <text y="-4">${esc(n.name)}</text>
      <text class="ip" y="13">${esc(ips.length > 26 ? ips.slice(0, 26) + "..." : ips)}</text>
      <text class="truthmark" y="43">actual fault</text></g>`;
  }
  svg.innerHTML = links + labels + nodes;
}

function highlightPath(flowId) {
  document.querySelectorAll(".link").forEach((l) => l.classList.remove("path"));
  const f = flowById(flowId);
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

// ---------------------------------------------------------------- verification panel
function renderFlows(state, changed) {
  const group = (title, flows) => `<div class="fgroup"><h4>${title} (${flows.length})</h4>` + flows.map((f) => {
    const ok = state ? state[f.id] : undefined;
    const allow = f.expect === "allow";
    let chip = '<span class="chip idle">not tested</span>';
    if (ok !== undefined) {
      chip = allow ? (ok ? '<span class="chip good">works</span>' : '<span class="chip bad">broken</span>')
                   : (ok ? '<span class="chip good">blocked</span>' : '<span class="chip bad">OPEN</span>');
    }
    return `<div class="frow ${changed && changed.has(f.id) ? "changed" : ""}">
      <div><div class="fid">${esc(f.id)}</div><div class="fpath">${esc(flowPath(f))}</div></div>${chip}</div>`;
  }).join("") + "</div>";
  $("flows").innerHTML = group("Must work", S.flows.filter((f) => f.expect === "allow")) +
                         group("Must stay blocked", S.flows.filter((f) => f.expect !== "allow"));
}

// ---------------------------------------------------------------- timeline
function addItem(tag, tagCls, body) {
  const li = document.createElement("li");
  li.innerHTML = `<span class="tag ${tagCls}">${esc(tag)}</span><div class="body">${body}</div>`;
  $("timeline").appendChild(li);
  const box = $("timeline");
  box.scrollTop = box.scrollHeight;
  return li;
}

function fmtArgs(args) {
  return Object.entries(args || {}).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(", ");
}

function longText(text, limit = 260) {
  if (text.length <= limit) return `<div class="note">${esc(text)}</div>`;
  return `<div class="note">${esc(text.slice(0, limit))}...</div><details><summary>full text</summary><pre>${esc(text)}</pre></details>`;
}

const STAGE_HTML = {
  REJECTED_BY_GATE: '<span class="stage bad"><b>Gate</b> refused</span><span class="stage skip"><b>Verifier</b> not reached, nothing changed</span>',
  ROLLED_BACK_COLLATERAL: '<span class="stage ok"><b>Gate</b> allowed</span><span class="stage warn"><b>Verifier</b> rolled back: it broke other flows</span>',
  ROLLED_BACK_NO_EFFECT: '<span class="stage ok"><b>Gate</b> allowed</span><span class="stage warn"><b>Verifier</b> rolled back: nothing improved</span>',
  COMMITTED: '<span class="stage ok"><b>Gate</b> allowed</span><span class="stage ok"><b>Verifier</b> kept: it fixed something and broke nothing</span>',
};
const NODE_CLASS = { COMMITTED: "committed", REJECTED_BY_GATE: "rejected", ROLLED_BACK_COLLATERAL: "rolled", ROLLED_BACK_NO_EFFECT: "rolled" };
const TAG_CLASS = { COMMITTED: "ok", REJECTED_BY_GATE: "bad", ROLLED_BACK_COLLATERAL: "warn", ROLLED_BACK_NO_EFFECT: "warn" };

function applyEvent(ev) {
  const d = ev.data;
  switch (ev.type) {
    case "run_started": {
      $("ticket").textContent = d.ticket;
      const f = flowById(d.reported_flow);
      const seeded = d.agent === "seeded" ? ' <span class="badge b-seeded">seeded demo, no model</span>' : "";
      const rebuilt = d.rebuilt_from_record ? " · timeline rebuilt from the run record" : "";
      $("run-meta").innerHTML = `${esc(whoName(d.agent, d.profile))}${d.model ? " (" + esc(d.model) + ")" : ""} · reported flow: ${esc(d.reported_flow)} ${f ? "(" + esc(flowPath(f)) + ")" : ""}${seeded}<br>${esc(d.run_id)}${rebuilt}`;
      highlightPath(d.reported_flow);
      break;
    }
    case "flows": {
      renderFlows(d.flows, d.stage === "final" ? S.changed : null);  // keep the last plan's highlight
      if (d.stage === "before") {
        const failing = Object.entries(d.flows).filter(([, v]) => !v).map(([k]) => k);
        addItem("Fault", "bad", `<div class="head">Fault injected: ${failing.length} of ${Object.keys(d.flows).length} flows fail</div><div class="note">${esc(failing.join(", "))}</div>`);
      }
      break;
    }
    case "model_call":
      if (d.text) addItem("Model", "think", longText(d.text));
      break;
    case "tool_call": {
      if (d.tool === "note_hypothesis") {
        const a = d.args || {};
        addItem("Hypothesis", "think", `<div class="head">${esc(a.hypothesis || "")}</div>${a.status ? `<div class="note">status: ${esc(a.status)}</div>` : ""}`);
      } else if (d.tool === "submit_plan") {
        addItem("Plan", "bad", `<div class="head">Plan not accepted</div><pre>${esc(d.output)}</pre>`);
      } else {
        addItem("Look", "", `<div class="tool">${esc(d.tool)} <span class="args">${esc(fmtArgs(d.args))}</span></div>
          <details><summary>output</summary><pre>${esc(d.output)}</pre></details>`);
      }
      break;
    }
    case "plan_submitted": {
      const rc = d.root_cause ? `<div class="rc">Root cause: <b>${esc(d.root_cause.device)} / ${esc(d.root_cause.fault_class)}</b>. ${esc(d.root_cause.summary)}</div>` : "";
      const why = d.plan.rationale ? longText(d.plan.rationale, 220) : "";
      const what = `${d.phase === "cleanup" ? "Cleanup plan" : "Plan"} ${d.index + 1} on ${esc(d.plan.device)}${d.profile ? " [" + esc(whoName("llm", d.profile)) + "]" : ""}`;
      S.planItems[d.index] = addItem(d.phase === "cleanup" ? "Cleanup" : "Plan", "plan",
        `<div class="head">${what}</div>${rc}${why}<pre class="cmds">${esc(d.plan.commands.join("\n"))}</pre>
         <div class="stages"><span class="stage"><b>Gate</b> checking...</span></div><div class="stage-detail"></div>`);
      S.planItems[d.index].dataset.device = d.plan.device;
      break;
    }
    case "plan_result": {
      const li = S.planItems[d.index];
      if (li) {
        li.querySelector(".tag").className = "tag " + (TAG_CLASS[d.outcome] || "");
        li.querySelector(".stages").innerHTML = STAGE_HTML[d.outcome] || `<span class="stage">${esc(d.outcome)}</span>`;
        const parts = [];
        if (d.gate_violations && d.gate_violations.length) parts.push(`<pre>${esc(d.gate_violations.join("\n"))}</pre>`);
        if (d.regressions && d.regressions.length) parts.push(`<div><span class="x">Broke:</span> ${esc(d.regressions.join(", "))}. Device restored: ${d.restored_ok ? "yes" : "NO"}.</div>`);
        if (d.improvements && d.improvements.length) parts.push(`<div><span class="y">${d.outcome === "COMMITTED" ? "Fixed" : "Would have fixed"}:</span> ${esc(d.improvements.join(", "))}</div>`);
        if (d.cleanup && d.drift_before !== null && d.drift_before !== undefined) parts.push(`<div>Leftover differences: ${d.drift_before} → ${d.drift_after ?? d.drift_before}</div>`);
        if (d.apply_errors && d.apply_errors.length) parts.push(`<pre>${esc(d.apply_errors.join("\n"))}</pre>`);
        li.querySelector(".stage-detail").innerHTML = parts.join("");
        markNode(li.dataset.device, NODE_CLASS[d.outcome]);
      }
      if (d.flows_now && Object.keys(d.flows_now).length) {
        S.changed = new Set([...(d.improvements || []), ...(d.regressions || [])]);
        renderFlows(d.flows_now, S.changed);
      }
      break;
    }
    case "drift":
      addItem("Drift", "warn", `<div class="head">Network healthy. ${d.count} leftover difference(s) from the intended configuration</div>
        <pre>${esc(Object.entries(d.items).map(([n, it]) => n + ": " + it.join("\n" + n + ": ")).join("\n"))}</pre>`);
      break;
    case "escalated":
      addItem("Escalate", "warn", `<div class="head">Escalated from ${esc(whoName("llm", d.from))} to ${esc(whoName("llm", d.to))}</div><div class="note">first attempt ended ${esc(d.first_outcome)}</div>`);
      break;
    case "run_finished": showSummary(d); break;
    case "saved": { const l = $("report-link"); if (l) l.hidden = false; break; }
    case "run_failed": addItem("Error", "bad", `<pre>${esc(d.error)}</pre>`); break;
  }
}

function showSummary(d) {
  for (const g of d.ground_truth || []) { const n = $("node-" + g.device); if (n) n.classList.add("truth"); }
  const cls = d.outcome === "FIXED_VERIFIED" ? "ok" : d.outcome === "ERROR" ? "" : d.outcome === "REJECTED_BY_GATE" || d.outcome === "ROLLED_BACK_COLLATERAL" ? "warn" : "bad";
  let why = "";
  if (d.outcome === "FIXED_VERIFIED") why = d.clean_fix ? "Clean: the configuration matches the intended one." : `${d.residual_count ?? "some"} leftover difference(s) remain.`;
  else if (d.outcome === "ROLLED_BACK_COLLATERAL") why = "The change broke other flows, so the device was restored.";
  else if (d.outcome === "REJECTED_BY_GATE") why = "The policy gate refused the plan. Nothing was changed.";
  const res = d.residual_items || {};
  const resTxt = Object.keys(res).length ? Object.entries(res).map(([n, items]) => `${n}: ${items.join("; ")}`).join("\n") : "none";
  const kpi = (k, v) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  const yn = (v) => (v === null || v === undefined ? "-" : v ? "yes" : "no");
  const box = $("summary");
  box.hidden = false;
  box.innerHTML = `<div class="verdict-line ${cls}"><span class="big">${esc(OUTCOME_TEXT[d.outcome] || d.outcome)}</span><span class="why">${esc(why)}</span></div>
    <div class="kpis">
      ${kpi("Security policy intact", d.policy_intact === false ? "NO" : yn(d.policy_intact))}
      ${kpi("Took the bait", d.trap_hits ? "yes" : "no")}
      ${kpi("Plans", d.plan_count ?? "-")}
      ${kpi("Gate refusals", d.gate_rejections ?? 0)}
      ${kpi("Verifier rollbacks", d.collateral_rollbacks ?? 0)}
      ${kpi("Diagnosis", d.diagnosis_correct === null || d.diagnosis_correct === undefined ? "-" : d.diagnosis_correct ? "correct" : "wrong")}
      ${kpi("Escalated", yn(d.escalated))}
      ${kpi("Cost", "$" + (d.cost_usd || 0).toFixed(4))}
      ${kpi("Time", (d.wall_seconds ?? "-") + " s")}
    </div>
    <div class="summary-foot">
      <span>Actual fault: <b>${esc((d.ground_truth || []).map((g) => g.device + " / " + g.fault_class).join(", ") || "-")}</b></span>
      <a id="report-link" href="/api/runs/${encodeURIComponent(S.runId)}/report" target="_blank" ${S.live ? "hidden" : ""}>Open incident report</a>
    </div>
    <details><summary>Leftover differences from the intended configuration</summary><pre>${esc(resTxt)}</pre></details>
    ${d.error ? `<pre>${esc(d.error)}</pre>` : ""}`;
  loadRuns();
}

// ---------------------------------------------------------------- playback of finished runs
const DELAY = { run_started: 700, flows: 900, model_call: 900, tool_call: 650, plan_submitted: 1400, plan_result: 2000,
                drift: 1600, escalated: 1600, run_finished: 500 };

function resetView() {
  clearInterval(S.timer);
  stopPlayback();
  S.after = 0; S.planItems = {}; S.changed = null;
  $("timeline").innerHTML = "";
  $("summary").hidden = true;
  drawTopology();
  renderFlows(null);
}

function stopPlayback() {
  clearTimeout(S.playTimer);
  S.playing = false;
  $("pl-play").textContent = "Play";
}

function updateBar() {
  $("pl-bar").style.width = S.queue.length ? `${(100 * S.qi) / S.queue.length}%` : "0";
}

function step() {
  if (S.qi >= S.queue.length) { stopPlayback(); updateBar(); return; }
  const ev = S.queue[S.qi++];
  S.after = ev.seq;
  applyEvent(ev);
  updateBar();
  if (!S.playing) return;
  const silent = ev.type === "model_call" && !ev.data.text;
  S.playTimer = setTimeout(step, silent ? 0 : (DELAY[ev.type] || 600) / S.speed);
}

function play() {
  if (S.qi >= S.queue.length) restart(false);
  S.playing = true;
  $("pl-play").textContent = "Pause";
  step();
}

function restart(autoplay = true) {
  const q = S.queue, rid = S.runId;
  resetView();
  S.queue = q; S.qi = 0; S.runId = rid;
  updateBar();
  if (autoplay) play();
}

function skipToEnd() {
  stopPlayback();
  while (S.qi < S.queue.length) { const ev = S.queue[S.qi++]; S.after = ev.seq; applyEvent(ev); }
  updateBar();
}

async function openRun(runId, animate = true) {
  resetView();
  S.runId = runId; S.live = false;
  document.querySelectorAll("#runs li").forEach((li) => li.classList.toggle("active", li.dataset.id === runId));
  S.queue = await api(`/api/runs/${encodeURIComponent(runId)}/events`);
  S.qi = 0;
  $("player").hidden = false;
  showTab("run");
  if (animate) play(); else skipToEnd();
}

// ---------------------------------------------------------------- live runs
async function poll() {
  const evs = await api(`/api/runs/${encodeURIComponent(S.runId)}/events?after=${S.after}`);
  for (const ev of evs) { S.after = ev.seq; applyEvent(ev); }
  if (evs.some((e) => e.type === "saved" || e.type === "run_failed")) {
    clearInterval(S.timer); S.live = false; setBusy(false);
    const link = $("report-link"); if (link) link.hidden = false;
  }
}

function setBusy(busy) {
  $("start").disabled = busy;
  document.querySelectorAll("[data-demo]").forEach((b) => (b.disabled = busy));
}

function followLive(runId) {
  resetView();
  $("player").hidden = true;
  S.runId = runId; S.live = true; setBusy(true);
  S.timer = setInterval(() => poll().catch((e) => ($("start-msg").textContent = e.message)), 700);
}

async function startRun() {
  const body = { fault_class: $("f-class").value, seed: +$("f-seed").value, agent: $("f-agent").value,
                 profile: $("f-agent").value === "llm" ? $("f-profile").value : null, split: $("f-split").value };
  $("start-msg").textContent = "";
  try {
    const r = await api("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    followLive(r.run_id);
  } catch (e) { $("start-msg").textContent = e.message; }
}

async function startDemo(btn) {
  const body = { kind: btn.dataset.demo, fault_class: btn.dataset.fault, seed: +btn.dataset.seed, split: "dev" };
  $("start-msg").textContent = "";
  try {
    const r = await api("/api/demo", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    followLive(r.run_id);
  } catch (e) { $("start-msg").textContent = e.message; }
}

async function loadRuns() {
  const runs = await api("/api/runs?limit=30");
  $("runs").innerHTML = runs.map((r) => {
    const fixed = r.outcome === "FIXED_VERIFIED";
    const b = fixed ? (r.clean_fix ? "b-ok" : "b-warn") : r.agent === "seeded" ? "b-seeded" : "b-bad";
    const label = fixed ? (r.clean_fix ? "clean fix" : "fixed") : (OUTCOME_TEXT[r.outcome] || r.outcome);
    const where = r.agent === "seeded" ? "seeded demo" : (r.split || "dev") + (r.label ? " · " + r.label : "");
    return `<li data-id="${esc(r.run_id)}" class="${r.run_id === S.runId ? "active" : ""}">
      <div><span class="badge ${b}">${esc(label)}</span></div>
      <div class="what">${esc(r.fault_class)} <span class="who">seed ${esc(r.seed)}</span></div>
      <div class="who">${esc(whoName(r.agent, r.profile))} · ${esc(where)}</div></li>`;
  }).join("") || '<li class="who">No runs yet</li>';
  $("runs").querySelectorAll("li[data-id]").forEach((li) => (li.onclick = () => openRun(li.dataset.id)));
}

// ---------------------------------------------------------------- results
const AGENT_ORDER = ["baseline", "spark-open", "spark-1.3", "router"];
const rowKey = (r) => (r.agent === "baseline" ? "baseline" : r.profile);
const frac = (k, n) => (n ? `${k}/${n}` : "-");
const ci = (c) => (c ? `${c[0].toFixed(2)} to ${c[1].toFixed(2)}` : "");
const countOf = (r, key, rateKey) => (r[key] !== undefined ? r[key] : Math.round((r[rateKey] || 0) * (r.runs - r.errors)));

function rateCell(k, n, interval) {
  if (!n) return "-";
  return `${k}/${n} (${(k / n).toFixed(2)})<span class="ci">95%: ${ci(interval)}</span>`;
}

function drawChart(rows) {
  const W = 760, rowH = 46, top = 10, left = 210, right = 90, plotW = W - left - right, H = top + rowH * rows.length + 30;
  const x = (v) => left + v * plotW;
  let g = "";
  for (const t of [0, 0.25, 0.5, 0.75, 1]) {
    g += `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${top}" y2="${H - 24}"/>
          <g class="axis"><text x="${x(t)}" y="${H - 6}" text-anchor="middle">${t.toFixed(2)}</text></g>`;
  }
  rows.forEach((r, i) => {
    const n = r.n ?? r.runs - r.errors, k = countOf(r, "fixed", "fix_rate");
    if (!n) return;
    const y = top + i * rowH + rowH / 2, c = r.fix_ci || [k / n, k / n];
    const name = whoName(r.agent, r.profile), ref = r.agent === "baseline" ? "ref" : "";
    const tip = `${name}: fixed ${k}/${n} (${(k / n).toFixed(2)}); 95% interval ${ci(c)}`;
    g += `<g class="row ${ref}" data-tip="${esc(tip)}">
      <rect class="hit" x="0" y="${y - rowH / 2}" width="${W}" height="${rowH}"/>
      <text class="label" x="${left - 14}" y="${y + 5}" text-anchor="end">${esc(name)}</text>
      <line class="ci-line" x1="${x(c[0])}" x2="${x(c[1])}" y1="${y}" y2="${y}"/>
      <circle class="pt" cx="${x(k / n)}" cy="${y}" r="6"/>
      <text class="value" x="${W - right + 14}" y="${y + 5}">${k}/${n}</text></g>`;
  });
  $("score-chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Share of runs fixed and verified, with 95% intervals">${g}</svg>
    <p class="hint" style="margin:6px 0 0">Dot: share of runs fixed and verified. Line: 95% interval. Gray: the scripted runbook, for reference.</p>`;
  $("score-chart").querySelectorAll(".row").forEach((el) => {
    el.onmousemove = (e) => { const t = $("tip"); t.hidden = false; t.textContent = el.dataset.tip; t.style.left = e.clientX + 14 + "px"; t.style.top = e.clientY + 14 + "px"; };
    el.onmouseleave = () => ($("tip").hidden = true);
  });
}

async function loadScore() {
  const labels = await api("/api/labels");
  const pick = $("score-label");
  const want = labels.length ? labels : [""];
  if (pick.options.length !== want.length) {
    pick.innerHTML = want.map((l) => `<option value="${esc(l)}">${esc(l || "all evals")}</option>`).join("");
    if (labels.includes("heldout-v1")) pick.value = "heldout-v1";
  }
  const label = pick.value, token = ++S.scoreToken;
  const s = await api(label ? `/api/scoreboard?label=${encodeURIComponent(label)}` : "/api/scoreboard");
  if (token !== S.scoreToken) return;   // a newer request (another label) is in flight; let it render
  const rows = [...s.rows].sort((a, b) => {
    const ia = AGENT_ORDER.indexOf(rowKey(a)), ib = AGENT_ORDER.indexOf(rowKey(b));
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  drawChart(rows);
  const agentCell = (r) => `<td class="agent">${esc(whoName(r.agent, r.profile))}<small>${r.agent === "baseline" ? "no model" : esc(r.profile)}</small></td>`;
  $("score").querySelector("thead").innerHTML = "<tr><th>Agent</th><th>Runs (errors)</th><th>Fixed and verified</th><th>Clean fix</th><th>Diagnosis correct</th><th>Cost per verified fix</th></tr>";
  $("score").querySelector("tbody").innerHTML = rows.map((r) => {
    const n = r.n ?? r.runs - r.errors;
    const cpf = r.cost_per_fix_usd ? "$" + r.cost_per_fix_usd.toFixed(4) : "-";
    const diag = r.agent === "baseline" ? "-" : frac(countOf(r, "diagnosis_correct", "diagnosis_rate"), n);
    return `<tr>${agentCell(r)}<td class="num">${r.runs} (${r.errors})</td><td class="num">${rateCell(countOf(r, "fixed", "fix_rate"), n, r.fix_ci)}</td>
      <td class="num">${rateCell(countOf(r, "clean", "clean_fix_rate"), n, r.clean_ci)}</td><td class="num">${diag}</td><td class="num">${cpf}</td></tr>`;
  }).join("");
  $("score-safety").querySelector("thead").innerHTML = "<tr><th>Agent</th><th>Security policy intact</th><th>Took the bait</th><th>Plans refused by the gate</th><th>Rolled back by the verifier</th><th>Escalated to Spark 1.3</th></tr>";
  $("score-safety").querySelector("tbody").innerHTML = rows.map((r) => {
    const n = r.n ?? r.runs - r.errors;
    const intact = r.policy_intact_n !== undefined ? frac(r.policy_intact, r.policy_intact_n) : (r.policy_intact_rate ?? "-");
    const esc_ = r.escalated_n ? frac(r.escalated, r.escalated_n) : "-";
    return `<tr>${agentCell(r)}<td class="num">${intact}</td><td class="num">${frac(r.runs_taking_bait ?? 0, n)}</td>
      <td class="num">${r.gate_rejections ?? 0}</td><td class="num">${r.collateral_rollbacks ?? 0}</td><td class="num">${esc_}</td></tr>`;
  }).join("");
  const classes = [...new Set(rows.flatMap((r) => Object.keys(r.by_class)))].sort();
  $("score-class").querySelector("thead").innerHTML = "<tr><th>Agent</th>" + classes.map((c) => `<th>${esc(c.replace(/_/g, " "))}</th>`).join("") + "</tr>";
  $("score-class").querySelector("tbody").innerHTML = rows.map((r) => `<tr>${agentCell(r)}` + classes.map((c) => `<td class="num">${esc(r.by_class[c] || "-")}</td>`).join("") + "</tr>").join("");
}

function showTab(which) {
  $("view-run").hidden = which !== "run";
  $("view-score").hidden = which !== "score";
  $("tab-run").classList.toggle("active", which === "run");
  $("tab-score").classList.toggle("active", which === "score");
  if (which === "score") loadScore().catch((e) => alert(e.message));
}

// ---------------------------------------------------------------- start
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
  $("f-profile").innerHTML = profiles.profiles.map((p) => `<option value="${esc(p.name)}" ${p.name === profiles.default ? "selected" : ""} ${p.key_present ? "" : "disabled"}>${esc(whoName("llm", p.name))}${p.key_present ? "" : " (no key)"}</option>`).join("");
  $("f-agent").onchange = () => ($("profile-row").hidden = $("f-agent").value !== "llm");
  $("start").onclick = startRun;
  document.querySelectorAll("[data-demo]").forEach((b) => (b.onclick = () => startDemo(b)));
  $("tab-run").onclick = () => showTab("run");
  $("tab-score").onclick = () => showTab("score");
  $("score-label").onchange = () => loadScore().catch((e) => alert(e.message));
  $("pl-play").onclick = () => (S.playing ? stopPlayback() : play());
  $("pl-restart").onclick = () => restart(true);
  $("pl-end").onclick = skipToEnd;
  $("pl-speed").onchange = () => (S.speed = +$("pl-speed").value);
  S.speed = +$("pl-speed").value;
  resetView();
  await loadRuns();
  const st = await api("/api/status");
  if (st.active) {
    S.runId = st.active; S.live = true; setBusy(true); $("player").hidden = true;
    S.timer = setInterval(() => poll().catch(() => {}), 700);
  }
  document.dispatchEvent(new Event("netproof-ready"));
}

init().catch((e) => { $("ticket").textContent = "Could not reach the API: " + e.message; });
