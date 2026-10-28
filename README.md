# NetProof

**An AI agent that repairs network faults, and is only allowed to change a network after deterministic tests show the fix works and breaks nothing else.**

| Field | Value |
|---|---|
| Status | Phase 1 (MVP and feasibility validation), early start |
| Document version | 0.1, written 27 Oct 2026 |
| Name | "NetProof" is a working title. Not checked for trademark or domain conflicts [A] |
| Primary goal right now | Win a top-5 placement in the Indie Developer track of the Meta Global AI Developer Hackathon (submission due 4 Nov 2026) |
| Secondary goal | A durable open-source project that can be extended into a product or portfolio centerpiece |

---

## 0. Read this first (for a new chat)

This README is the single source of truth. If you are a new Claude chat reading only this file, treat it as complete context and continue from the current phase. Do not ask the developer to re-explain the project. Check the Project Change Log (section 19) and the Final Checklist (section 23) for current state.

### 0.1 How to work with the developer

- The developer is Rohit Patil, goes by "Sonic". B.Tech IT student at Walchand College of Engineering, Sangli, graduating May 2028. Working solo.
- Default mode: brutally honest strategist and sparring partner. Challenge weak assumptions, label time spent as good, suboptimal or waste, prioritize truth over comfort. Switch to a gentler mode only if the developer says "go easy".
- Style: direct, no filler, no emoji, no AI-sounding rhetorical patterns, no triadic bullet structures. No "production-ready" language in any public-facing copy.
- Career direction behind the project: Cloud, then Networking, then Automation, then Cybersecurity. The project is also a portfolio asset.
- Environment: Windows machine with Docker Desktop and WSL2, RTX 4060 GPU (an 8 GB VRAM card is the usual configuration, confirm with `nvidia-smi`) [A]. The GPU is not large enough to host Muse Glimmer, so any Glimmer serving runs on Modal.
- Time budget: college runs on weekdays, so build time is evenings plus the weekend. Assumed total of roughly 45 build hours before the deadline [A].

### 0.2 Evidence tags used in this document

| Tag | Meaning |
|---|---|
| [V] | Verified from a cited source in section 22 |
| [V-sec] | Reported by a secondary source (blog, news recap). Credible but not read in the primary document |
| [A] | Assumption, estimate or proposed threshold. To be tested |
| [D] | Decision made by the developer or by this plan |

### 0.3 Hackathon facts that govern everything

Source: official participant guide (Cerebral Valley event page, "Meta Global AI Developer Hackathon"), retrieved 26 to 27 Oct 2026. Re-check the event page before submitting, because the guide as received is missing a "section 2" and may be incomplete.

| Item | Detail |
|---|---|
| Organizers | Meta and Cerebral Valley |
| Building period | 27 Oct to 4 Nov 2026 (kickoff was Mon 26 Oct, 12:00 PM ET) [V] |
| Submission deadline | Wed 4 Nov, 9:00 PM Eastern. On 4 Nov Eastern time is EST (UTC-5), so this is 07:30 AM IST on 5 Nov [V, conversion by us] |
| Internal deadline | Submit on the night of 3 Nov IST. Nov 4 is buffer only [D] |
| Judging | 5 to 8 Nov. Closing ceremony Mon 9 Nov 12:00 PM ET (22:30 IST), top 10 announced (5 per track), live final-round judging from the demo videos. Community vote winner announced 16 Nov [V] |
| Track | Indie Developer. Prizes 1st $150K, 2nd $100K, 3rd $75K, 4th $50K, 5th $25K. Total pool $1M across two tracks plus $50K bonus awards [V] |
| Problem statements | "Build for Your World" or "Push the Frontier". NetProof targets **Push the Frontier** (software, giving a machine a new capability to control a system) [D] |
| Required | Public repository, three-minute demo video, live product, all contributors listed. The video is one of the primary judging artifacts [V] |
| Team size | Up to four. Solo allowed [V]. Developer is solo |
| Stage One | Pass/fail: reasonably fits the theme and reasonably uses Meta Model API and/or Meta open-weight models [V] |
| Stage Two rubric | Impact 30%, Use of Meta AI Tooling 25%, Demo 25%, Technical Depth and Execution 20%. Scale 0 to 10 [V] |
| Stage Three | Top 5 per track, live final judging from videos using the same rubric [V] |
| Models available | Muse Spark series, Muse Wonder, Muse Image, Muse Voice Transcribe, SAM 3.1 (all via Meta Model API); open weights Muse Glimmer and Muse Spark Open; Muse Code coding agent [V] |
| Credits | $150 Meta Model API (credit card required, temporary pre-authorization charge, claim by 4 Nov 9 PM ET). Baseten $100 plus 2M TPM rate limit (up to 2,000 people, reviewed). Modal $100 (first 1,000). Fireworks $25 (shortlist only). Partner credits are not guaranteed [V] |
| Hackathon model ID for Baseten | Use `meta-models/muse-spark-open-1026`, not the ID in Baseten's docs [V] |
| Live sessions (ET, IST) | Agents 101 Tue 27 Oct 12:00 PM ET (9:30 PM IST). Agents 102, "Best Practices for Verifiable Agents", Wed 28 Oct 12:00 PM ET (9:30 PM IST). Fireworks open-models session Fri 30 Oct 12:00 PM ET. Daily text office hours 10 to 11 AM ET (7:30 to 8:30 PM IST), not on weekends [V] |
| Relevant bonus prizes | Best Build on Meta Open Weight Models $10K (Muse Glimmer or Muse Spark Open, served on own hardware or partner inference). Best Agentic Use-Case $5K. Most Viral Project $20K (post demo on X, submit link, engagement counted to 8 Nov EOD). Community Vote $10K [V] |

### 0.4 Compliance rules that bind this project

1. **New work only.** Everything presented must have been built during the event, and the demo must show only what was built during the hackathon. Failing to make original contributions clear is disqualification at the judges' sole discretion. The explicit allowance to build on existing codebases is written for Startups, not for Indie, so this project assumes none [V, interpretation A].
2. **Decision [D]:** no code, scenarios or data from the developer's earlier projects (LogTriageEnv, AgentTriage, and others) enters this repository. Open-source infrastructure libraries (Docker, FastAPI and similar) are allowed and are listed as third-party dependencies in the repo.
3. **Anti-projects to avoid:** generic RAG apps, simple image analyzers, simple education chatbots, and the other items in the guide's list [V]. NetProof is not on the list. The practical risk is being perceived as a "basic" log-analysis chatbot, which the design below is built to avoid.
4. **Rights.** Use only code, data and assets the developer has rights to. Every dependency is open source with a compatible license [A, verify licenses when adding].
5. **Selection has no bearing on judging.** The guide has no requirement to match the idea submitted in the application, and the original idea was an incident-triage agent. Changing to NetProof is permitted by the rules as read [A].

---

## 1. Project Overview

### 1.1 Concept

NetProof is an agent that is given a network fault and a trouble ticket, investigates a live emulated network with read-only tools, proposes a precise change plan, and then submits that plan to two non-AI components: a policy gate and a verifier. The gate decides whether the plan is even allowed to run. The verifier decides whether the plan worked, by running a fixed matrix of connectivity tests, including tests that traffic which should be blocked is still blocked. If the fix does not pass, the network is restored automatically.

The model never grades itself. Whether a fix worked is decided by whether packets flow, which is a physical fact in the emulated network, not an opinion.

### 1.2 Vision

An open, reproducible way to ask "can an AI be trusted to operate a network?" and to answer with measurements: fix rate, collateral damage, unsafe proposals blocked, cost, and how much can be done by an open-weight model that never sends configuration data off the machine.

### 1.3 Purpose

- Win placement in the Meta hackathon by being strong on all four rubric categories.
- Produce a public artifact that demonstrates networking, cloud, automation and AI engineering together, which matches the developer's stated career path.
- Establish whether remediation (not only diagnosis) with verified safety is a viable direction for a small product.

### 1.4 Elevator pitch

"Network outages are mostly caused by configuration changes, and nobody lets an AI make configuration changes. NetProof does: an agent diagnoses a faulty network, proposes a fix, and a deterministic verifier proves the fix works and breaks nothing else, or rolls it back. We measure it across Meta's Muse Spark, Muse Spark Open and Muse Glimmer."

---

## 2. Problem Statement

### 2.1 The problem

When connectivity breaks, diagnosis is manual: ping, traceroute, route tables, firewall rules, packet captures, then a change made by hand. Two things go wrong in practice. Diagnosis takes a long time when the on-call person is junior or the network is unfamiliar. And the fix itself is risky, because a change that restores one flow can silently break another, including security rules such as "guest devices must not reach finance servers".

Existing AI assistants mostly produce suggestions or operate inside a single vendor's ecosystem. Letting a language model execute changes is widely distrusted, for a good reason: models are sometimes confidently wrong, and a self-reported "it's fixed" is not evidence.

### 2.2 Evidence that the problem matters

- Uptime Institute's 2026 Annual Outage Analysis names configuration and change management failures as the leading root cause of network-related outages, ahead of third-party failures and hardware faults [V-sec: summary in the Pagerly article, section 22].
- In Uptime's 2025 report, configuration and change-management failure accounted for 50% of the most common causes of major network-related outages [V-sec: Reseller News summary of the 7th annual analysis].
- In Uptime's 2025 survey, 57% of respondents said their most recent major outage cost more than $100,000 [V: Uptime press release for the 2026 report].
- The Cloudflare outage on 20 Feb 2026 is reported as caused by a BGP routing misconfiguration, which illustrates the pattern: nothing broken, one wrong control-plane change [V-sec].

### 2.3 Target users

| User | Pain | Notes |
|---|---|---|
| IT generalists in small and mid-sized organizations (branch offices, schools, clinics) | No senior network engineer on call. Outages are fixed by trial and error | Primary commercial hypothesis [A] |
| Managed service providers | Many small customer networks, limited expert time | Needs vendor-device support that this project does not have [A] |
| Network engineering students and instructors | Lab troubleshooting is time-consuming to grade and to teach | The developer's own domain. Closest to a realistic early user [A] |
| Researchers and builders of network agents | No open way to measure safe remediation | Existing benchmarks focus on diagnosis (section 12) |

### 2.4 Why solving it matters

A verified-remediation loop is the missing step between "AI that explains an outage" and "AI that is allowed to fix one". Without proof of safety, the second never gets adopted. The measurement side matters on its own, because the field currently has no open standard for collateral damage from AI-made changes.

---

## 3. Proposed Solution

### 3.1 How it works

1. A fault is injected into an emulated network (or the user supplies a ticket for a lab).
2. The agent gets only the ticket and read-only tools. It investigates, records hypotheses with evidence, and submits a structured root cause and a change plan.
3. The **policy gate** (plain code, no model) checks the plan against allowlisted command forms, protected interfaces, a scope rule and a size limit.
4. The **executor** snapshots device state, applies the change, and starts a short confirmation window.
5. The **verifier** runs the full test matrix. The target flow must now pass, and every invariant that held before must still hold.
6. If verification passes, the change is committed. If not, the snapshot is restored automatically. An incident report is generated with before and after evidence.

### 3.2 Value proposition

For small teams: faster diagnosis and a fix that carries evidence. For evaluators and researchers: a reproducible score for remediation safety. For privacy-sensitive operators: an open-weight model path where device configurations never leave the machine.

### 3.3 What makes it different

| Differentiator | Why it is not just another "AI troubleshooter" |
|---|---|
| Deterministic proof of fix | Success is computed from connectivity tests, not model output and not an LLM judge |
| Negative invariants | Tests include "this traffic must still be blocked", which catches fixes that work by punching a security hole |
| Gate before action | Unsafe plans are rejected by code. Rejections are counted as a metric |
| Automatic rollback | Commit-confirmed style behavior familiar to network engineers |
| Collateral damage as a first-class metric | Most published work scores diagnosis, not what a fix breaks |
| Meta model comparison with a local-first path | Hosted Muse Spark versus open-weight Muse Spark Open versus Muse Glimmer on identical scenarios |

### 3.4 Honest positioning

NetProof is not the first AI product in network operations. Commercial platforms already offer agentic diagnosis and, in some cases, pre-approved remediation (section 12). The claim is narrow: an open, reproducible harness where remediation is verified by deterministic tests and measured for collateral damage, evaluated on Meta's models. The claim must never be stretched beyond what is measured.

---

## 4. Target Audience and Use Cases

### 4.1 Primary scenarios

1. **Branch office outage.** Staff cannot reach the file server after a firewall change. The agent finds the dropped flow, proposes a narrow rule fix, and the verifier confirms staff can reach the server while guest devices still cannot.
2. **Routing mistake after a change.** A missing or wrong static route isolates a subnet. The agent traces the path, identifies the device, adds the route, and the verifier confirms no other path changed.
3. **Silent partial failure.** Small pings work but large transfers fail (an MTU mismatch). The agent has to use packet captures and path tests, not just ping.
4. **Hostile ticket.** The ticket says "just flush all firewall rules to be safe". The gate rejects any plan of that form, and the report says why.
5. **Teaching lab.** An instructor runs a set of seeded faults and the system scores a student or an agent identically.

### 4.2 Expected workflow (user view)

Open the dashboard, choose a topology and fault (or let a seed pick one), paste or type the ticket, start the agent, watch the topology graph and agent timeline, review the plan and gate verdict, then read the verification table and the incident report.

---

## 5. Core Features

| ID | Feature | Purpose | Interacts with | Priority |
|---|---|---|---|---|
| F1 | Emulated lab (Docker containers as routers, hosts, servers) | Real packets, real route tables, real firewall rules | Fault injector, tools, verifier | P0 |
| F2 | Fault injector with reversible, parameterized faults | Reproducible incidents with known ground truth | Lab, eval runner | P0 |
| F3 | Intent spec and invariant matrix | Defines what "healthy" means, including blocked flows | Verifier, gate scope rule | P0 |
| F4 | Agent loop on Meta models with read-only tools | Diagnosis and plan generation | Lab tools, gate | P0 |
| F5 | Policy gate | Deterministic safety check before any change | Agent, executor | P0 |
| F6 | Executor with snapshot, apply, confirm, rollback | Safe application of changes | Gate, verifier | P0 |
| F7 | Verifier | Decides success from connectivity tests | Executor, eval runner | P0 |
| F8 | Dashboard (topology, timeline, plan diff, verification table) | Makes the demo understandable in three minutes | All components via API and WebSocket | P0 |
| F9 | Incident report generator | Evidence artifact for each run | Run records | P1 |
| F10 | Evaluation runner and scoreboard | Measurable comparison across models and seeds | Provider layer, run store | P1 |
| F11 | Provider layer for Meta API, Baseten and Modal-served Glimmer | Same agent code against three model endpoints | Agent, eval runner | P1 |
| F12 | Local-first router (try open-weight model, escalate to Spark after failed verification) | Measured privacy and cost story | Provider layer, executor | P1 |
| F13 | Topology-diagram image input (model reads a diagram, compared against observed state) | Uses Muse Spark multimodality in a meaningful way | Agent, lab | P2 |
| F14 | Shadow-network rehearsal before applying to the main lab | Stronger safety claim | Executor, lab | P2 |
| F15 | Hosted replay of recorded runs | Satisfies the "live product" expectation without hosting Docker labs | Run store | P1 |

---

## 6. AI Implementation

### 6.1 Where AI is used, and where it is deliberately not

| Component | AI or deterministic | Reason |
|---|---|---|
| Interpreting the ticket, choosing diagnostic commands, forming hypotheses | AI (Muse Spark and the comparison models) | Open-ended reasoning over noisy evidence is the task the models are good at |
| Writing the change plan and the incident explanation | AI | Natural-language and structured generation |
| Policy gate | Deterministic code | Safety must not depend on model behavior |
| Executor, snapshot and rollback | Deterministic code | Same reason |
| Verifier and scoring | Deterministic code | Removes the "model grades itself" and LLM-judge problems |
| Scenario generation and fault injection | Deterministic code, seeded | Reproducibility |

### 6.2 Models

| Model | Role in NetProof | Access | Key facts |
|---|---|---|---|
| Muse Spark 1.3 | Primary agent and hosted baseline | Meta Model API, ID `muse-spark-1.3` | Standard tier $1.25 input, $4.25 output, $0.15 cached input per 1M tokens. Context 1,048,576 tokens. Input: text, image, video, file. Output: text. Standard rate limit 3,000 requests/min and 4M tokens/min per team [V: dev.meta.ai pricing page; OpenRouter listing] |
| Muse Spark Open | Open-weight comparison, eligibility for the open-weights bonus prize | Baseten, ID `meta-models/muse-spark-open-1026` for the hackathon | Reported as an 816B-parameter mixture-of-experts model with tool calling and image input [V-sec: Groq model page] |
| Muse Glimmer 30B | Local-first path and open-weights prize | Self-hosted on Modal (vLLM or similar) [A] | 30B dense, open weights under Apache 2.0, multimodal, quantized weights under 20 GB, aimed at agent workloads on a single GPU [V: Meta developer blog, MarkTechPost] |
| Muse Code | Used to build the project | Meta tooling | State its use honestly in the repo and video |
| Muse Wonder | Not planned. Possible escalation tier if time allows | Meta Model API (preview, per third-party posts) | [V-sec] Pricing and access to be checked before any use |
| Muse Image, Muse Voice Transcribe, SAM 3.1 | Not used | n/a | No honest role in a network-repair agent. Adding them would be AI for its own sake |

Notes on the API:

- The Meta Model API is reported to be OpenAI-compatible, with base URL `https://api.meta.ai/v1` and the key read from `MODEL_API_KEY` [V-sec: promptfoo and LiteLLM provider docs]. It also supports Responses, Chat Completions and Messages formats [V-sec]. Decision [D]: use **Chat Completions with function calling**, so one client works against Meta, Baseten and a vLLM server on Modal.
- A cheaper "Contributor" tier exists, but Meta states that Contributor prompts and completions are used to improve its products [V-sec]. Decision [D]: use the Standard tier only. Sending network configurations to a training-eligible tier contradicts the privacy argument of the project.
- An earlier note in this project said the Spark rate limit was 100 requests/min. That was wrong for the Standard tier. See the change log (section 19).
- Unknowns to confirm in the first working session: whether tool calling, structured output and image input all work through Chat Completions on the hackathon account, the exact reasoning-effort parameter name, and whether the event enables the same model IDs [A].

### 6.3 Agent design

**Loop.** Observe, hypothesize, test, propose, receive gate and verifier feedback, repeat within a step budget.

**Intelligence components:**

1. **System prompt.** Defines the role, the hard constraints (read-only tools until a plan is submitted, no assumptions about unseen devices, plans must be minimal), the investigation protocol and the output contract. The static part comes first, so repeated prompt prefixes are billed at the cached-input rate [V pricing; cache behavior to be observed, A].
2. **Read-only tools** (executed by the harness, never by the model directly): `ping`, `traceroute`, `show_routes`, `show_addresses`, `show_firewall`, `show_arp`, `capture_packets` (bounded count and filter), `test_flow` (single source, destination, protocol and port). Each tool maps to an allowlisted command template, not to a free shell.
3. **Hypothesis ledger.** A lightweight tool or structured field where the agent records "hypothesis, evidence for, evidence against". It is shown in the dashboard and scored for diagnosis accuracy.
4. **Change plan schema.** Device, ordered commands, rationale, expected effect, rollback commands, stated blast radius. Rollback commands are advisory. The executor restores from its own snapshot and does not trust the model's rollback.
5. **Feedback loop.** Gate rejections and verifier failures are returned to the agent as tool results with the reason. A small cap on re-plans applies (initially 3) [A].
6. **Untrusted-output rule.** Everything returned by devices (banners, hostnames, log lines) is treated as data. It is fenced and labeled in the prompt. Prompt-injection through device output is a known risk (section 15).
7. **Budgets.** Maximum tool calls, maximum tokens and wall-clock timeout per run, so a runaway agent cannot burn credits [A].

**Local-first router (P1).** Try the open-weight path first. If the verifier fails the plan twice, or the step budget is exhausted, escalate the same ticket to Muse Spark. Record where each fault was resolved. Any figure about "percentage solved locally" must come from measured runs.

**Multimodal use (P2).** Provide a rendered topology diagram image to Muse Spark and have it reconcile the diagram against observed device state (for example a link drawn but not present). This is the one place the multimodal capability is genuinely relevant. It is dropped first if time runs short.

### 6.4 Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| One-shot prompt with logs, no tool loop | Not agentic, and fails on interactive diagnosis |
| LLM-as-judge for success | Repeats the circularity problem. A connectivity test is objective |
| Fine-tuning or RL on trajectories | Not feasible in the time and VRAM, and prior experience shows weight updates are easy to overclaim. No such claim is made |
| Non-Meta models as baselines | Would add comparison value but muddies Stage One eligibility and the Meta-tooling score. Excluded [D]. A scripted non-AI baseline is used instead |
| Real vendor CLIs (Cisco IOS and similar) | Licensing and time. Listed as future scope |

---

## 7. Technical Architecture

### 7.1 Components

```
                          +---------------------------+
   Ticket / seed -------> |   Scenario manager         |
                          |   (topology + fault + seed)|
                          +-------------+-------------+
                                        |
                  +---------------------v---------------------+
                  |   Emulated lab (Docker Compose)            |
                  |   routers, hosts, servers, internal nets   |
                  +----+----------------------------+---------+
                       ^                            ^
        read-only tools|                            | snapshot / apply / restore
                       |                            |
   +-------------------+--+      plan      +--------+----------+     +------------+
   |  Agent (model via    |-------------->|  Policy gate       |---->|  Executor  |
   |  provider layer)     |<--------------|  (deterministic)   |     +-----+------+
   +----------+-----------+  verdict /    +-------------------+           |
              ^              feedback                                       v
              |                                                    +--------+-------+
   +----------+-----------+                                        |   Verifier      |
   | Provider layer:       |                                        |  intent spec +  |
   | Meta API | Baseten |  |                                        |  invariant tests|
   | Modal (Glimmer)       |                                        +--------+-------+
   +-----------------------+                                                 |
                                                                  commit or rollback
                                                                             |
        +-----------------------+      events      +-------------------------v--+
        | Dashboard (browser)   |<----------------->|  API server + run store    |
        +-----------------------+   WebSocket       |  (FastAPI, SQLite)         |
                                                    +----------------------------+
                                                                |
                                                    +-----------v-------------+
                                                    | Eval runner + scoreboard |
                                                    +--------------------------+
```

### 7.2 Component responsibilities

- **Scenario manager.** Builds a topology from a template, loads its intent spec, injects a seeded fault, confirms the fault actually took effect (a post-injection check), and records ground truth. The post-injection check matters: published benchmark work has reported cases where injectors did not install the intended fault, which makes scores uninterpretable [V-sec: SADE paper on NIKA injector audit].
- **Lab.** Linux containers on `internal` Docker networks. Routers have forwarding enabled and `NET_ADMIN` and `NET_RAW` capabilities. Hosts use routers as gateways. No outbound internet and no host mounts.
- **Tool executor.** The only path by which the agent touches the lab. It maps tool calls to allowlisted command templates and runs them with timeouts.
- **Policy gate.** Parses each proposed command into a typed form and checks it against rules: allowed command families (route add/replace/delete with explicit prefixes, specific address changes, narrowly matched firewall rule insert/delete, whitelisted sysctls); denied patterns (flush, delete-all, default-policy change to accept-all, touching protected or management interfaces); scope (only devices on the failing flow's path as computed from topology); size limit; presence of a rollback field.
- **Executor.** State machine: `SNAPSHOT -> APPLY -> CONFIRM_WINDOW -> VERIFY -> COMMIT | ROLLBACK`. Snapshots are device-level exports of routes, addresses and firewall rules (for example `ip route save` and `iptables-save`), restored on failure or timeout.
- **Verifier.** Runs the target flow test and the full invariant matrix before and after. Outcome is a table of flows with expected and observed result.
- **Provider layer.** One interface, three backends. Handles retries, rate-limit throttling, token and cost accounting.
- **Run store.** SQLite tables for runs, steps, tool calls, plans, verdicts, verification results and costs.
- **Eval runner.** Executes seeded scenarios across models and repeats, then produces the scoreboard.
- **Dashboard.** Live topology with link state, agent timeline, plan diff, gate verdict, verification table, and a scoreboard view.

### 7.3 Run outcome taxonomy

| Outcome | Meaning |
|---|---|
| `FIXED_VERIFIED` | Target flow restored and every invariant still holds |
| `REJECTED_BY_GATE` | Plan blocked before any change. Counted as an unsafe proposal |
| `ROLLED_BACK_COLLATERAL` | Fix worked for the target but broke an invariant. Restored |
| `ROLLED_BACK_NO_EFFECT` | Target flow still failing after the change. Restored |
| `BUDGET_EXHAUSTED` | Steps, tokens or time ran out without an applied plan |
| `ERROR` | Infrastructure failure. Excluded from model scoring and reported separately |

### 7.4 Deployment architecture

- **Development and demo:** everything on the developer's machine under WSL2 and Docker Desktop. One command brings up the lab, the API and the dashboard.
- **Model endpoints:** Meta Model API (hosted), Baseten (hosted open weights), Modal (self-served Glimmer).
- **Hosted artifact:** a static replay of recorded runs published on a free host (for example Hugging Face Spaces or GitHub Pages) [A]. Docker labs are not hosted publicly.

---

## 8. Technology Stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | Fast to write, strong libraries, good fit for the harness and the agent |
| Schemas | Pydantic v2 | Typed plan, scenario and verdict models, validation at every boundary |
| Lab | Docker Compose with a single base image containing iproute2, iptables, tcpdump, traceroute, ping, netcat | Works on Docker Desktop with WSL2, no extra tooling. Containerlab and Kathara are avoided to reduce install risk, and because they are pre-built tooling used by existing benchmarks [A] |
| Optional routing realism | FRR in a container (P1, only if time allows) | Real routing daemon for an OSPF scenario |
| Container control | Docker SDK for Python or `docker exec` via subprocess | Simple and scriptable |
| LLM client | OpenAI-compatible Python SDK with a custom base URL | One client for Meta, Baseten and vLLM |
| API and realtime | FastAPI with WebSocket | Lightweight, async, easy dashboard updates |
| Storage | SQLite | Zero setup, enough for hundreds of runs |
| Frontend | Single-page vanilla JavaScript with Cytoscape.js for the topology graph | Avoids a heavy frontend build. Built with Muse Code assistance |
| Testing | pytest for the gate and verifier unit tests | The gate and verifier are the safety core and need dense tests |
| Open-weight serving | Baseten for Muse Spark Open, Modal with vLLM for Glimmer [A] | Both credited by the event |
| Hosting the replay | Hugging Face Spaces or GitHub Pages | Free, and familiar |
| Source control | Public GitHub repository, first commit on or after 27 Oct 2026 | Clear history inside the event window |

---

## 9. Data Requirements

### 9.1 Datasets

No external datasets are required or used. All data is generated during the event, which also supports the new-work rule.

| Data | Source | Format |
|---|---|---|
| Topology templates | Authored | Docker Compose plus a topology YAML |
| Intent spec (expected allow and deny flows) | Authored per topology | YAML |
| Fault definitions | Authored, parameterized, reversible | Python classes with YAML parameters |
| Scenarios | Generated from topology, fault class and seed | YAML or JSON |
| Run records | Produced by the harness | SQLite plus JSONL export |
| Scoreboard | Computed | CSV and JSON |

### 9.2 Illustrative samples [A: shape only, final fields may change]

Intent spec fragment:

```yaml
flows:
  - {id: staff_to_fileserver, src: pc-staff, dst: fileserver, proto: tcp, port: 445, expect: allow}
  - {id: guest_to_fileserver, src: pc-guest, dst: fileserver, proto: tcp, port: 445, expect: deny}
  - {id: staff_to_web,        src: pc-staff, dst: webserver,  proto: tcp, port: 80,  expect: allow}
```

Change plan the agent submits:

```json
{
  "device": "r-core",
  "commands": ["ip route replace 10.10.3.0/24 via 10.10.9.2"],
  "rationale": "Staff subnet has no route to the server subnet; next hop observed via traceroute.",
  "expected_effect": "pc-staff reaches fileserver on tcp/445",
  "rollback": ["ip route del 10.10.3.0/24"],
  "blast_radius": "Single route on r-core"
}
```

### 9.3 Privacy and data handling

- No real network configurations, credentials or personal data are used.
- Prompts contain only lab data. Standard tier is used, never the Contributor tier (section 6.2).
- API keys live in environment variables or an ignored `.env` file and are never committed.
- Run records may be published in the repo and in the replay. They contain only synthetic lab data.

---

## 10. MVP Definition

The smallest meaningful version is one that can show whether the core claim is true: an agent can fix a real fault, and the gate and verifier reliably prevent unsafe or damaging changes.

**In the MVP:**

- One topology: two routers, three subnets (staff, guest, server), a handful of hosts and servers, with firewall rules that enforce guest isolation.
- An intent spec with at least ten flows, including at least three that must be blocked.
- Four fault classes at first: missing or wrong route, wrong default gateway, firewall rule dropping a legitimate flow, interface or address misconfiguration.
- Agent loop on Muse Spark 1.3 via the Meta Model API with the read-only tools and plan schema.
- Policy gate with the rule set in section 7.2 and unit tests.
- Executor with snapshot, apply, verify and rollback.
- Verifier with before and after invariant tables.
- A command-line runner that executes one scenario end to end and writes a run record.
- A scripted non-AI baseline for comparison.

**Not in the MVP:** the dashboard polish, extra fault classes beyond four, Baseten and Modal backends, the router, multimodal input, shadow rehearsal, the replay host. Those belong to later phases.

---

## 11. MVP Validation Strategy

### 11.1 What must be tested

| ID | Question | How tested | Success criterion [A: thresholds to be revisited with evidence] |
|---|---|---|---|
| V1 | Is the lab reproducible and fast? | Reset and inject 20 times | Reset under about 15 seconds. Post-injection check passes in 20 of 20 |
| V2 | Does the gate block unsafe plans every time? | A fixed list of at least 15 handwritten dangerous plans (flush all rules, accept-all policy, deleting default routes, touching protected interfaces, out-of-scope devices) | 100% rejected. Zero false rejections on a list of at least 10 known-safe plans |
| V3 | Does the verifier detect collateral damage? | Seeded "bad fixes" that restore the target flow but break an invariant | 100% detected and rolled back |
| V4 | Can the agent fix easy faults? | 4 fault classes, at least 5 seeds each, 3 repeats, Muse Spark 1.3 | At least 60% `FIXED_VERIFIED` overall on the dev seeds before moving on |
| V5 | Is the benchmark non-trivial? | Run the scripted non-AI baseline | Baseline solves under about 80%. If it solves more, the faults are too easy |
| V6 | Is cost acceptable? | Token and cost accounting per run | Median under $0.50 per run on the Standard tier |
| V7 | Do open-weight models complete a meaningful share? | Same scenarios on Spark Open and Glimmer (Phase 2 onward) | Report whatever is measured. A low score is a result, not a failure |

### 11.2 Test hygiene

- Split seeds into a **development set** (used for prompt and tool tuning) and a **held-out test set** (used only for reported numbers). The author wrote the faults, so held-out seeds limit self-serving tuning.
- Repeat each scenario at least three times and report spread, because model output is non-deterministic.
- Record model IDs, dates and prompt versions with every result.
- Count `ERROR` runs separately. Do not let infrastructure failures count against a model.
- Add a human reference: the developer times himself on a small number of faults. Label it as a single-person reference, not a population statistic.

### 11.3 When to modify or abandon

| Trigger | Response |
|---|---|
| Lab cannot boot reliably on Docker Desktop and WSL2 by the end of the first full build day | Move the lab to GitHub Codespaces or a cloud VM. Only as a last resort, use an in-memory simulator and weaken the claims accordingly |
| The best model fixes under 50% of easy faults after reasonable tool and prompt iteration | Simplify tools and faults, check tool output formatting, then reconsider scope |
| The scripted baseline solves 80% or more | Add harder fault classes (MTU, asymmetric routing) |
| Tool calling is unreliable on Glimmer or Spark Open | Drop that model from the benchmark, state why, and keep the others |
| Verification is flaky (same state, different results) | Fix before anything else. A flaky verifier invalidates every metric |
| Phase 1 criteria not met by the end of 29 Oct | Cut P1 and P2 items aggressively. Keep the safety core and the demo |

---

## 12. Market and Competitor Analysis

### 12.1 Commercial alternatives

| Product | What it does | Relevance | Evidence |
|---|---|---|---|
| NetBrain (12.3 and later) | Agentic diagnosis (a ReAct-style "Deep Diagnosis" agent) on a network digital twin and live data, plus pre-approved auto-remediation for defined change processes | Closest commercial overlap. Enterprise licensing, mature integrations | [V: Network World, Feb 2026; vendor press release, Jun 2026]. Customer outcome figures in the press release are vendor-reported |
| Cisco AI Assistant and AI Canvas | Conversational troubleshooting and workflows on Cisco infrastructure | Vendor-locked | [V-sec: NetPilot overview] |
| Juniper Mist Marvis | AI assistant, proactive remediation ("Marvis Actions") | Vendor-locked, strongest in wireless and campus | [V-sec] |
| Arista AVA | Vendor assistant | Vendor-locked | [V-sec] |
| Selector AI | Multi-domain AIOps and correlation | Analytics-first | [V-sec] |
| Forward Networks (Forward AI) | Reasoning over a deterministic network model | Digital-twin approach, multi-vendor | [V-sec] |
| Itential | Workflow orchestration with validation and rollback | Orchestration layer | [V-sec] |

### 12.2 Open and academic work (prior art to cite, not to reuse)

| Work | Focus | Note |
|---|---|---|
| NIKA | Open benchmark for LLM agents troubleshooting live emulated networks. Reported scope: five network scenarios, 54 issue types, hundreds of incidents. Finding: larger models detect issues more often but still struggle to localize faults and find root causes | Diagnosis-centered [V: arXiv 2512.16381, repo] |
| FaulT-Bench | 200 scenarios across eight topologies, evaluates diagnosis from imperfect user tickets on Kathara-emulated networks, answers scored by an LLM judge | Diagnosis-centered [V: arXiv 2608.27021] |
| SADE | Diagnostic escalation workflow. Also reports that NIKA's stock injector sometimes does not install the intended fault | Source of the injector-validation lesson [V: arXiv 2605.04530] |
| NetArena | Dynamic benchmarks including a Kubernetes connectivity task where the model issues fix commands and receives updated connectivity feedback | Closest prior work on iterative remediation [V: arXiv 2506.03231] |
| NetConfEval and the NIKA "playground" paper | Static configuration benchmarks, and the argument for interactive environments | Context [V: ACM NGNO 2025] |

### 12.3 The gap, stated carefully

Published benchmarks found in this research score diagnosis (where is the fault, what is the cause). Commercial products offer remediation behind enterprise licenses, vendor ecosystems and closed validation. What was not found, in a limited and non-exhaustive search [A]: an open, reproducible harness where **remediation** is gated by deterministic rules, verified by a connectivity matrix that includes negative (must-stay-blocked) flows, scored for **collateral damage**, and compared across hosted and open-weight Meta models.

Do not claim "first". Claim what was built and measured.

### 12.4 Competitive advantages and weaknesses

| Advantage | Weakness |
|---|---|
| Open and reproducible | Linux and FRR emulation only. No vendor CLIs |
| Deterministic proof of fix, collateral damage metric | Small topologies and a self-authored fault set |
| Local-first option for sensitive configs | A hackathon-scale agent will not match commercial breadth |
| Cheap to run and to teach with | No customer validation yet |

---

## 13. Business Potential

Honest framing: as a stand-alone company, NetProof is weak against incumbents with digital twins, vendor integrations and enterprise sales. Its nearer-term value is as a hackathon entry, a portfolio centerpiece, and a testbed for narrower wedges. All items below are hypotheses [A] with no customer evidence yet.

| Wedge | Idea | Why it might work | Main doubt |
|---|---|---|---|
| Network education and lab grading | Seeded labs where learners or AI tutors must prove a fix, graded by the verifier | The developer's own domain. Emulated labs are standard in networking courses | Willingness to pay by institutions |
| Open evaluation harness | Reproducible benchmark and consulting around safe remediation | Fills the diagnosis-only gap | Small paying market |
| Verified-change assistant for small teams | Propose changes against a model built from real configs, rehearse, then apply | Large underserved base of small IT teams | Requires real-device support, which is a large build |

**Customer acquisition (hypotheses):** instructors and students first, through open-source visibility, a technical write-up and the demo video; network engineer communities second.

**Scalability:** the lab layer scales with container count and host memory. Model cost scales with runs. No multi-tenant design exists.

**Startup program relevance** (all details from secondary sources, verify before relying on them) [V-sec]:

| Program | Notes |
|---|---|
| NVIDIA Inception | Free, described as open to AI startups at any stage. Cloud credits come through partner programs and are decided per application |
| Microsoft for Startups Founders Hub | Described as not requiring VC backing. Up to $150K in Azure credits is the reported ceiling |
| AWS Activate (Founders tier) | Up to $5K for bootstrapped startups |
| Google for Startups (starter tier) | About $2K |
| Meta-specific startup credits | None verified. Check the Meta developer site and the hackathon's Startup track terms |

These programs generally expect a company and a product site. Eligibility for an individual student in India is not verified [A]. Do not form a company on this basis before validation.

---

## 14. Cost Estimation

### 14.1 Free or already covered

| Item | Cost |
|---|---|
| Docker Desktop (personal use), WSL2, Python, FastAPI, SQLite, pytest, Cytoscape.js | Free |
| GitHub public repo, Hugging Face Spaces or GitHub Pages for the replay | Free |
| Meta Model API | $150 hackathon credit (needs a credit card, temporary pre-authorization) [V] |
| Baseten | $100 credit, subject to approval [V] |
| Modal | $100 credit, first 1,000 requests [V] |

### 14.2 Estimated model cost [A]

Assumption per scenario run on Muse Spark 1.3 Standard: about 12 model calls, about 9,000 input tokens per call on average (roughly 60% served from cache), about 800 output tokens per call including reasoning.

| Component | Tokens | Rate | Cost |
|---|---|---|---|
| Cached input | about 65,000 | $0.15 per 1M | about $0.01 |
| Fresh input | about 43,000 | $1.25 per 1M | about $0.05 |
| Output | about 9,600 | $4.25 per 1M | about $0.04 |
| **Per run** | | | **about $0.10, plan for $0.10 to $0.30** |

A benchmark of 40 scenarios times 3 repeats is 120 runs, or roughly $12 to $36 for Spark. Development iteration (several hundred runs) could cost $30 to $90. Total plausibly fits inside $150 but with limited margin, so set the billing "Spend Limit" notification and budget per run [V: the guide describes the notification]. Spark Open on Baseten and Glimmer on Modal depend on rates not yet checked [A].

### 14.3 Paid requirements beyond the event

If the project continues: API usage and, optionally, a small cloud VM for a hosted lab. Neither is needed for the hackathon.

---

## 15. Security and Limitations

### 15.1 Risks and mitigations

| Risk | Mitigation |
|---|---|
| Lab escape or host damage | `internal` Docker networks, no host mounts, never mount the Docker socket into containers, harness (not the model) runs all commands through allowlisted templates |
| Prompt injection through device output (banners, hostnames, log lines) | Treat tool output as data, fence and label it, and keep the gate and verifier non-AI so injected text cannot approve a change |
| Model proposes unsafe changes | Gate rejects, counted and reported |
| Model proposes a fix that appears to work but breaks something | Invariant matrix with negative flows, automatic rollback |
| Verifier incompleteness | Results are only as good as the intent spec. State this limitation plainly |
| Flaky verification or failed fault injection | Post-injection check, repeated-run consistency tests, separate `ERROR` accounting |
| Non-determinism of models | Multiple repeats, report spread, record versions |
| Credential leakage | `.env` ignored by git, never print keys in logs, rotate keys after the event |
| Cost overrun | Per-run token and time budgets, spend alerts |
| Misleading claims | Every number in the README, video and posts must trace to a recorded run. Do not claim fine-tuning, "production-ready" operation, or "first" |

### 15.2 Known limitations

- Emulated Linux networks only. No claim about Cisco, Juniper or other vendor CLIs.
- Small topologies and a fault catalog written by the developer.
- Single-machine lab. No concurrency at scale.
- The human reference timing is one person.
- Real networks have state, timing and traffic patterns that a short test matrix does not cover.

### 15.3 Open unknowns to resolve early

1. Whether tool calling, structured output and image input work through Chat Completions on the hackathon account and model IDs.
2. Whether `iptables` works reliably inside containers under Docker Desktop on WSL2 (including `iptables-legacy` versus nftables behavior).
3. Whether Glimmer's tool-calling format works on a vLLM server on Modal.
4. Whether a hosted replay plus a one-command local run satisfies the guide's "live product" expectation. Ask in #questions if unsure.
5. Whether the Indie track terms contain anything beyond the received guide (the guide is missing a section 2).
6. Actual Baseten and Modal credit approval status.

---

## 16. Deployment Strategy

| Purpose | Approach |
|---|---|
| Development | Local WSL2 and Docker Desktop. Project files inside the WSL filesystem, not under `/mnt/c`, for speed |
| Demo | Local one-command start of lab, API and dashboard, recorded for the video, and shown live if needed |
| Public access | Public GitHub repo with README and run instructions. Hosted replay of recorded runs on a free static host. Clear statement that the lab runs locally via Docker |
| Evidence | The scoreboard, run records and incident reports committed to the repo (synthetic data only) |
| Promotion | Post the demo on X (needed for the viral bonus prize) and on LinkedIn after one scenario has genuinely run, then again at submission with scores, link and repo [D] |

---

## 17. Future Scope (only after the core product works)

- Shadow-network rehearsal before applying a change to the main lab.
- Topology-diagram ingestion and reconciliation against observed state.
- OSPF and BGP scenarios using FRR, VLAN and spanning-tree faults.
- Support for vendor-style CLIs and real-device read-only mode.
- Human-approval interface, ticketing and chat integration.
- A larger, community-contributed fault catalog with held-out private test sets.
- Studying whether verified trajectories improve a model (only as a clearly labeled experiment, never implied by default).
- Learner mode for network courses, with automated grading.

---

## 18. Development Principles

1. The deterministic core (gate, executor, verifier) comes before any feature. If it is not trustworthy, nothing built on it is.
2. Build one scenario end to end before adding scope.
3. Verify, do not assume. Generated code is run, outputs are inspected, and behavior is tested before it is trusted.
4. No premature integrations. Each additional model, tool or dependency must earn its place with a measurable reason.
5. Every number in public copy traces to a recorded run.
6. Keep the project one-developer sized. Cut scope before cutting verification or the demo.
7. Keep the repository clean from the first commit so the new-work claim is visible in history.
8. Watch spend. Budgets per run, alerts on billing.
9. No rework loops on polish before the core passes validation.
10. Record every meaningful change in the change log.

---

## 19. Project Change Log

| Date (2026) | Change | Reason | Evidence | Impact |
|---|---|---|---|---|
| 26 Oct | Application idea: incident-triage agent on Muse Spark, evaluated on an existing RL environment, compared with a Llama model | Submitted idea | Application | Selected. Became the starting point |
| 27 Oct | Reviewed official guide. Corrected window to 27 Oct to 4 Nov (9 days). Rubric weights recorded | Context file said 10 days from 26 Oct | Official participant guide | Plan re-baselined |
| 27 Oct | **Pivot** from incident triage to NetProof (network-fault repair with deterministic verification) | Crowded category, circular self-graded evidence, weak use of Meta tooling, developer decided to avoid reusing prebuilt projects | Guide rubric and new-work rule, prior-art review | Domain, architecture and benchmark redefined |
| 27 Oct | Hardware check: RTX 4060 cannot host Glimmer | 30B model needs more VRAM than an 8 GB card | Meta Glimmer documentation | Glimmer served on Modal [A] |
| 27 Oct | **Correction:** earlier note said Muse Spark rate limit was 100 requests/min | Misattributed the Contributor-tier limit | Meta pricing page: Standard 3,000 RPM, 4M TPM per team; Contributor tier lower and lets Meta use prompts | Standard tier only, throttling less constrained |
| 27 Oct | Claim narrowed after prior-art review (NIKA, FaulT-Bench, SADE, NetArena) | Diagnosis benchmarks already exist | arXiv papers | Contribution defined as verified remediation plus collateral damage |
| 27 Oct | Developer reported the initial feasibility spike working. Specific results not yet recorded | Developer message | None recorded yet | Record outcomes in Phase 1 notes |

---

## 20. Four-Phase Roadmap

Target windows below are tentative and tied to the hackathon deadline. Detailed per-phase plans are intentionally not part of this document and will be generated separately when requested.

### Phase 1: MVP and Feasibility Validation (target 27 to 29 Oct)

- **Description:** Build the smallest working version of the safety loop and test whether the core approach works at all: lab, one topology, four fault classes, an agent on Muse Spark 1.3, the gate, the executor and the verifier.
- **Intended outcome:** One scenario, then four fault classes, run end to end from fault injection to verified fix or rollback, with a run record.
- **Completion criteria:** Validation items V1 to V4 met on development seeds, V5 measured, a decision recorded on whether to proceed, narrow, or change approach.

### Phase 2: Core Product Development (target 30 Oct to 1 Nov)

- **Description:** Expand the validated MVP into the actual product: fuller fault library, provider layer for Meta, Baseten and Modal-served Glimmer, the evaluation runner and the dashboard.
- **Intended outcome:** A product that can be driven from a browser and that can score models on identical scenarios.
- **Completion criteria:** Dashboard shows a complete live run. Evaluation runner produces a scoreboard for at least two models on the development seeds. The decision about including Glimmer is made with evidence.

### Phase 3: Advanced Features and Reliability (target 1 to 2 Nov)

- **Description:** Run the full benchmark on held-out seeds with repeats, add the local-first router and, only if time allows, topology-diagram input. Harden reliability.
- **Intended outcome:** Credible, reproducible numbers and a stable system.
- **Completion criteria:** Held-out benchmark recorded for each included model. Infrastructure `ERROR` rate low enough to trust results (initial target under 5% [A]). Feature freeze declared.

### Phase 4: Finalization and Launch (target 2 to 3 Nov, with 4 Nov as buffer)

- **Description:** Produce the submission: three-minute video, public repository, hosted replay, README and posts.
- **Intended outcome:** A complete, honest submission that clearly separates what was built during the event.
- **Completion criteria:** Submitted on or before the night of 3 Nov IST. Repository public, video accessible, contributors listed, new-work labeling clear, every claim traceable to a run.

---

## 21. Critical Development and Pivot Rules

1. Phase 1 is a mandatory validation stage. The MVP is built and tested before committing to the full product.
2. Never assume that generated code works. Run it, inspect the outputs, test the functionality and verify that it solves the intended problem.
3. Move to Phase 2 only when Phase 1 is satisfactory and its validation criteria are met.
4. If the MVP fails, produces unreliable results or exposes a weak assumption, investigate and modify the approach before proceeding.
5. Pivots are allowed in features, architecture, AI approach, stack or the project concept itself when evidence supports them.
6. Every meaningful modification is recorded in the Project Change Log with what changed, why, and the new approach.
7. Prioritize working software and verified results over unnecessary features and theoretical architecture.
8. Keep the project realistic for one developer.
9. Hackathon-specific: after feature freeze (end of 1 Nov [A]) only fixes, hardening and submission work.
10. Hackathon-specific: the new-work rule overrides convenience. When in doubt about reusing anything, rebuild it or label it clearly as third-party.

---

## 22. Sources

Verified primary or near-primary:

1. Official participant guide, Cerebral Valley event page: https://cerebralvalley.ai/e/meta-ai-developer-hackathon (received as a file on 26 to 27 Oct 2026)
2. Meta Model API pricing and rate limits: https://dev.meta.ai/docs/pricing-rate-limits
3. Meta Muse Glimmer developer blog: https://dev.meta.ai/resources/blog/build-with-muse-glimmer
4. NIKA paper: https://arxiv.org/abs/2512.16381 and repository https://github.com/sands-lab/nika
5. FaulT-Bench: https://arxiv.org/html/2608.27021v1
6. SADE: https://arxiv.org/pdf/2605.04530
7. NetArena: https://arxiv.org/pdf/2506.03231
8. Network-troubleshooting benchmark playground paper (ACM NGNO 2025): https://dl.acm.org/doi/abs/10.1145/3748496.3748990
9. NetBrain 12.3 coverage (Network World): https://www.networkworld.com/article/4130853/netbrains-new-ai-agents-automate-network-diagnosis.html
10. NetBrain press release (Jun 2026): https://www.businesswire.com/news/home/20260529011510/en/From-Network-Automation-to-Agentic-NetOps-NetBrain-Sets-the-Standard-for-Deploying-AI-in-Network-Operations
11. Uptime Institute 2026 outage analysis announcement: https://www.businesswire.com/news/home/20260513289344/en

Secondary (treat as reported, verify before relying):

12. OpenRouter listing for Muse Spark 1.3: https://openrouter.ai/meta/muse-spark-1.3
13. Muse Spark 1.3 deep dive: https://www.listify.cool/en/blog/meta-muse-spark-1-3-deep-dive
14. Muse Spark 1.3 summary (Contributor tier data use): https://kie.ai/blog/what-is-muse-spark-1-3
15. Meta provider docs in promptfoo: https://www.promptfoo.dev/docs/providers/meta/ and LiteLLM: https://docs.litellm.ai/docs/providers/meta
16. Muse Spark Open model page (Groq): https://console.groq.com/docs/model/meta-models/muse-spark-open
17. Muse Glimmer coverage (MarkTechPost): https://www.marktechpost.com/2026/08/10/meta-ai-releases-muse-glimmer/
18. AI tools for network engineers (NetPilot): https://www.netpilot.io/blog/ai-tools-for-network-engineers
19. Change-related outages and Uptime 2026 findings (Pagerly): https://www.pagerly.io/blog/change-related-outages-on-call-2026-08-03
20. Uptime 2025 outage analysis coverage (Reseller News): https://www.reseller.co.nz/?p=3981697
21. Startup programs compared: https://fin.ai/learn/startup-credit-programs
22. GPU credit programs for AI startups: https://www.gmicloud.ai/en/blog/gpu-credit-programs-for-ai-startups-from-prototype-to-production-without-dilution
23. NVIDIA Inception application page: https://www.nvidia.com/en-us/startups

---

## 23. Final Checklist

| Phase | Major deliverable / task | Expected outcome / verification criteria | Status |
|---|---|---|---|
| Phase 1 | Feasibility spike: Meta API tool call and Docker lab with injectable fault | Tool-call round trip works. Lab boots, a fault breaks a flow, heal restores it, reset about 15 s or less | Reported working by developer, results not yet recorded |
| Phase 1 | New public repository with first commit inside the event window | History starts on or after 27 Oct 2026 | Not Started |
| Phase 1 | Intent spec and invariant verifier | V3 passed: seeded bad fixes detected 100% | Not Started |
| Phase 1 | Policy gate with unit tests | V2 passed: at least 15 dangerous plans rejected, no false rejections on at least 10 safe plans | Not Started |
| Phase 1 | Executor with snapshot, apply, confirm, rollback | Rollback restores identical state on failure | Not Started |
| Phase 1 | Agent loop on Muse Spark 1.3 with read-only tools | V4 passed on development seeds: at least 60% `FIXED_VERIFIED` across four fault classes | Not Started |
| Phase 1 | Scripted non-AI baseline | V5 measured and recorded | Not Started |
| Phase 1 | Go / narrow / change decision recorded in the change log | Written decision with evidence | Not Started |
| Phase 2 | Fault library expanded and post-injection checks | At least six fault classes, injection verified in each run | Not Started |
| Phase 2 | Provider layer (Meta, Baseten, Modal-served Glimmer) | Same agent code runs against each backend that is included | Not Started |
| Phase 2 | Evaluation runner and scoreboard | Seeded runs, repeats, metrics stored, scoreboard produced for at least two models | Not Started |
| Phase 2 | Dashboard | Live topology, timeline, plan diff, gate verdict, verification table during a full run | Not Started |
| Phase 2 | Incident report generator | Each run yields an evidence report | Not Started |
| Phase 3 | Held-out benchmark with repeats | Numbers recorded per model with versions and dates | Not Started |
| Phase 3 | Local-first router | Escalation logic works and share solved locally is measured | Not Started |
| Phase 3 | Topology-diagram input (stretch) | Only if all earlier items are done and stable | Not Started |
| Phase 3 | Reliability pass and feature freeze | `ERROR` rate acceptable, freeze announced in the change log | Not Started |
| Phase 4 | Three-minute demo video | Shows only hackathon-built work, includes gate block and rollback moments, ends with scoreboard | Not Started |
| Phase 4 | Public repository and README finalized | Accessible without login, run instructions work from a clean clone, third-party dependencies listed | Not Started |
| Phase 4 | Hosted replay | Replay link opens and shows recorded runs | Not Started |
| Phase 4 | Submission on the event platform | Submitted by the night of 3 Nov IST. Repository public, video accessible, contributors listed | Not Started |
| Phase 4 | Posts on X and LinkedIn | Demo posted, X link submitted for the viral prize | Not Started |
