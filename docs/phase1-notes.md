# Phase 1 notes

## Environment
- Host: Windows 11, native Windows Python + Docker Desktop (WSL2 backend). No Ubuntu WSL distro is installed, so the repo lives at `C:\Users\Rohit\Desktop\netproof` instead of `~/netproof` in WSL
- Docker server version: 29.7.2 (kernel 6.6.87.2-microsoft-standard-WSL2). iptables 1.8.9 (nf_tables) works inside the lab containers
- Python version: 3.11.0
- Model IDs visible to the key (28 Oct 2026): muse-image-1.0, muse-spark-1.1, muse-spark-1.2, muse-spark-1.2-contributor, muse-spark-1.3, muse-spark-1.3-contributor, muse-voice-transcribe-1.0, muse-wonder-1.0, sam-3.1
- Tool calling: yes   JSON mode: yes   reasoning_effort: accepted (`low` and `minimal` both accepted; runs used `low`)
- Pricing check (dev.meta.ai pricing page, 28 Oct): Spark 1.1, 1.2 and 1.3 share one Standard price ($1.25 in / $0.15 cached / $4.25 out per 1M). No cheaper non-contributor Spark model exists, so `muse-spark-1.3` stays
- Model and prompt for all paid runs: `muse-spark-1.3`, reasoning_effort `low`, PROMPT_VERSION `p1.1`

## Validation results
| ID | Criterion | Result | Pass? | Evidence (command / file) |
|---|---|---|---|---|
| V1 | reset <= ~15 s, injection check 20/20 | median 2.4 s, max 3.1 s, 20/20 | yes | `python -m netproof.cli validate-lab --n 20` |
| V2 | gate: >=15 dangerous rejected, >=10 safe allowed | 27/27 dangerous rejected, 13/13 safe allowed, all catalog fixes and bad fixes pass | yes | `pytest tests/test_gate.py` (42 passed) |
| V3 | bad fixes rolled back with identical state | 9/9 bad fixes rolled back with identical state, 12/12 correct fixes committed and healthy | yes | `python -m netproof.cli validate-verifier` |
| V4 | >=60% FIXED_VERIFIED on dev seeds | 12/12 (100%), every variant once, diagnosis_correct 12/12 | yes, on a reduced sample | `runs/eval-20261028-213047-llm/summary.json` |
| V5 | scripted baseline fix rate (measured) | 20/20 (100%) on seeds 0-4 | measured | `runs/eval-20261028-212508-baseline/summary.json` |
| V6 | median cost per run < $0.50 | median $0.0228, total $0.27 for 12 runs (plus $0.023 for the first single run) | yes | llm summary above |

Full automated suite: `NP_DOCKER=1 pytest` gave 79 passed (64 unit, 15 Docker).

Other llm eval figures: gate_rejections 1, collateral_rollbacks 0, errors 0, median 31.7 s per run, 4 to 7 model calls per run.

V4 sample reduction: the plan asks for seeds 0-4 x 3 repeats (60 runs). To save credits, each of the 12 variants was run once (seeds 0-2). Seeds 3 and 4 only re-use variants a and b with the other ticket wording, so variant coverage is complete, but there is no repeat spread yet. Re-run with repeats when the held-out benchmark is built (Phase 3).

First paid run (route_missing seed 0, record `runs/20261028-213038-llm-route_missing-s0-r0.json`):
1. Investigated before acting: tested three flows, traced two paths, read routes on both routers, addresses and firewalls, recorded a hypothesis with evidence, then submitted.
2. Plan was minimal: one command, `ip route add 10.10.3.0/24 via 10.10.9.2` on r-edge.
3. Root cause named r-edge and `route_missing`.
4. Cost $0.0231; 18,110 prompt tokens of which 6,882 were cached; 1,879 completion tokens.

Human reference timing: not done yet (needs the developer with a stopwatch).

## Failures worth remembering
- Windows `subprocess` text mode turned `\n` into `\r\n` on stdin, which broke `iptables-restore` in the containers. `DockerLab.exec` now sends bytes.
- The plan's pre-commit hook rejected its own file (the regex text matched itself) and the plan doc (example keys). Both are excluded from the key scan only.
- Gate gap found in review: `ip route del default` was allowed, but README V2 lists deleting default routes as dangerous. Rule and 2 test cases added; system prompt updated (p1.0 -> p1.1).
- interface_down seed 0: first plan rejected by the gate for missing rollback commands; the model resubmitted with rollback and fixed it. Feedback loop works.
- firewall_drop seed 2 (r-edge drops all guest traffic): the agent inserted a narrow ACCEPT for guest -> webserver tcp/80 above the faulty DROP instead of deleting the DROP. Verified healthy, but less minimal than the reference fix and it leaves the bad rule in place. "Minimality" is not scored yet.
- The scripted baseline solves 100%. The four Phase 1 fault classes are too easy to show what the model adds.

## Decision (go / narrow / change) and why
**Go to Phase 2, with two conditions.**

V1, V2 and V3 pass on the real lab, so the safety core (gate, executor, verifier) can be trusted. V4 passes at 100% with correct diagnoses and V6 is about 20x under the cost limit. But V5 shows the baseline also solves 100%, so the current benchmark cannot separate the model from a runbook. Conditions for Phase 2:
1. Add harder fault classes (MTU, asymmetric routing, overlapping or shadowed firewall rules, multi-device faults, misleading tickets) until the baseline drops below about 80%.
2. Before quoting any number publicly, re-run V4 with repeats on held-out seeds.
