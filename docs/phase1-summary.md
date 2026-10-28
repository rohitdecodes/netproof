# Phase 1 Summary

Phase 1 (MVP and feasibility validation) closed on 28 Oct 2026. Decision: **Go to Phase 2, with conditions.** Full numbers are in `docs/phase1-notes.md`; the plan that was followed is `docs/phase1-plan.md`.

## What was built

| Component | Files | State |
|---|---|---|
| Docker lab: 2 routers, 4 hosts, 4 networks, 11-flow intent spec (5 allow, 6 deny) | `lab/` | Healthy, reset in about 2.4 s |
| Lab control: provisioning, snapshot/restore, flow tests | `netproof/lab.py`, `topology.py`, `intent.py` | Working |
| Fault catalog: 4 classes x 3 variants, seeded tickets, fixes and bad fixes | `netproof/faults.py` | 12/12 inject and heal |
| Policy gate (no model) | `netproof/gate.py`, `schemas.py` | 27 dangerous / 13 safe cases |
| Executor: gate, snapshot, apply, verify, commit or rollback | `netproof/executor.py` | Working |
| Agent loop on Muse Spark 1.3 with 8 read-only tools plus `submit_plan` | `netproof/agent.py`, `tools.py`, `llm.py`, `records.py` | Working, prompt `p1.1` |
| Scripted non-AI baseline | `netproof/baseline.py` | Working |
| CLI: lab-up/down, provision, check, scenarios, inject, run, eval, validate-lab, validate-verifier | `netproof/cli.py` | Working |
| Tests | `tests/` | 79 pass (64 unit, 15 Docker) |

## Validation results

| ID | Result | Pass |
|---|---|---|
| V1 lab | reset median 2.4 s, max 3.1 s; post-injection check 20/20 | yes |
| V2 gate | 27/27 dangerous rejected, 13/13 safe allowed | yes |
| V3 verifier | 9/9 bad fixes rolled back to identical state; 12/12 correct fixes committed | yes |
| V4 agent | 12/12 FIXED_VERIFIED, diagnosis correct 12/12 (each variant once) | yes, reduced sample |
| V5 baseline | 20/20 FIXED_VERIFIED | measured: faults too easy |
| V6 cost | median $0.023 per run; total paid spend in Phase 1 about $0.30 | yes |

Verifier stability: 5/5 identical checks. Gate rejections in the paid eval: 1 (missing rollback, model fixed it on resubmit). Collateral rollbacks by the model: 0.

## Plan changes made during execution

1. **Windows instead of WSL.** No Ubuntu distro existed under WSL. Everything runs with native Windows Python 3.11 and Docker Desktop 29.7.2. Repo path is `C:\Users\Rohit\Desktop\netproof`. Use `.venv\Scripts\python` instead of `source .venv/bin/activate`.
2. **CRLF fix in `lab.py`.** Windows text-mode stdin turned `\n` into `\r\n` and broke `iptables-restore`. `DockerLab.exec` now sends stdin as bytes.
3. **Pre-commit hook.** The plan's hook blocked itself and the plan doc (both contain the key pattern as text). Those two paths are excluded from the key scan; everything else is still scanned.
4. **Gate rule added.** `ip route del default` was allowed; now rejected (README V2 names it dangerous). System prompt updated to match, `PROMPT_VERSION` p1.0 to p1.1.
5. **Paid eval trimmed for credits.** 12 runs (each variant once, seeds 0-2, 1 repeat) instead of 60 (seeds 0-4, 3 repeats). `NP_REASONING_EFFORT=low`. No cheaper allowed model exists: Spark 1.1, 1.2 and 1.3 have the same Standard price, and the `-contributor` models are excluded by the privacy decision.
6. **No `phase1` branch.** Work was committed step by step directly to `main`.
7. **`.gitattributes`** forces LF line endings, since lab files run inside Linux containers.

## Issues and findings to carry into Phase 2

- **The benchmark is too easy.** The baseline runbook fixes 100%, the same as the model. Phase 2 needs harder fault classes (MTU, asymmetric routing, shadowed or overlapping firewall rules, faults spread across two devices, misleading tickets) until the baseline drops below about 80%.
- **No real rollback by the model yet.** Collateral rollbacks were 0, so a demo of an automatic rollback currently needs a seeded bad fix. Harder faults should produce real ones.
- **Minimality is not scored.** On `firewall_drop` seed 2 the model added an ACCEPT above the faulty DROP instead of deleting it. Verified healthy, but it leaves the bad rule. Consider a minimality or "residual bad rule" metric.
- **No repeat spread.** V4 is a single run per variant. Repeats belong in the Phase 3 held-out benchmark.
- **Runs are slow because of `docker exec`.** Median 31.7 s per agent run and about 9 s per baseline run. That's fine now, but it will matter for 100+ run benchmarks.
- **Cost headroom is large.** About $0.023 per run means a 120-run benchmark costs about $3, so there is room for Spark Open and Glimmer comparisons and for raising reasoning effort if harder faults need it.
- **Model IDs visible to the key:** muse-spark-1.1/1.2/1.3 (plus contributor variants), muse-wonder-1.0, muse-image-1.0, muse-voice-transcribe-1.0, sam-3.1. Muse Spark Open and Glimmer are not on this key; they need Baseten and Modal.

## Still open (needs the developer)

- Human reference timing on 3 faults (stopwatch, about 20 minutes).
- Meta billing spend notification (M5), and Baseten and Modal credit forms (M6).
- GitHub secret scanning push protection (repository Settings, then Code security).
- The two earliest commits carry a Co-Authored-By trailer; removing it needs a history rewrite and force push.
