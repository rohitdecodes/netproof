# Phase 2 notes

## Progress log (29 Oct 2026)
| Step | State | Evidence |
|---|---|---|
| 0 | Done | 79 passed (64 unit, 15 Docker), HEALTHY, tag v0.1-phase1 present. README change log and limitations updated. Hook now scans MODEL/BASETEN/GLIMMER keys and refuses a staged test file holding a fake Baseten key; `docs/phase_2.md` excluded from the key scan (it quotes the pattern) |
| 1 | Done | 13-flow HEALTHY; 5/5 lab tests incl. PMTU black hole (MTU mechanism works under Docker Desktop) |
| 2 | Done | 48 gate tests (31 dangerous, 15 safe, 2 others), 3 tools tests |
| 3 | Done | 27/27 variants break their reported flow and heal on reset |
| 4 | Done | 18 new/updated unit tests; full unit suite green; prompt p2.0 |
| 5 | Done | validate-verifier 27/27 clean fixes and 21/21 bad fixes rolled back identically; validate-lab 27/27, reset median 3.5 s, max 3.7 s; baseline mtu_mismatch s0 fails with residual `mtu eth1 1500 -> 1200` and the OUTPUT frag-needed DROP |
| 7, 8 | Code done | fastapi 0.162, uvicorn 0.54, httpx 0.28 installed; tests/test_server.py 3 passed; app.js syntax checked. UI checklist pending (needs a browser) |
| 9 | Code done | scripts/smoke_llm.py and deploy/modal_glimmer.py compile. Not run |
| 6 (baseline) | Done | eval-20261029-090307-baseline-difficulty: 12/27 fixed (0.444) |
| 7 (API check) | Done | `np serve`: /api/topology 6 nodes and 13 flows, /api/catalog 9 classes, /api/profiles 4 (spark-1.3 key present), /api/scoreboard, /docs 200. Baseline run started over the API: events run_started, flows, run_finished, saved in order; a second start got 409; report served |

Full suite after Step 5: `NP_DOCKER=1 pytest` 126 passed (94 unit, 32 Docker).

Deviation: the plan file is `docs/phase_2.md`, not `docs/phase2-plan.md`.

## Difficulty gate (Step 6)
- Baseline eval id: eval-20261029-090307-baseline-difficulty
- Baseline fix rate (all 27): 0.444 (12/27)   Phase 1 classes: 12/12   New classes: 0/15
- Per class: route_missing 3/3, wrong_gateway 3/3, firewall_drop 3/3, interface_down 3/3, mtu_mismatch 0/3, wrong_nexthop 0/3, acl_typo 0/3, multi_fault 0/3 (s0 and s1 ended COMMITTED, partial fix, network still unhealthy), misleading_ticket 0/3. Errors 0, median 11.3 s per run
- Spark hard-fault smoke runs (class, outcome, clean, diagnosis, cost):
- Human reference (fault, minutes, notes):
- Decision: pass / add harder faults

## Second model (Step 9)
- Baseten: credits status, model id that worked, tool calling yes/no
- Glimmer on Modal: deployed yes/no, tool calling yes/no, latency per call, GPU minutes used
- Glimmer decision and evidence:

## Phase 2 evaluation (Step 10)
| Agent / profile | Eval id | Runs | Fix rate | Clean fix rate | Diagnosis | Collateral | Gate | Median $ | Median s |
|---|---|---|---|---|---|---|---|---|---|

## Validation results (Step 11)
| ID | Criterion | Result | Pass? | Evidence |
|---|---|---|---|---|

## Failures worth remembering

## Decision (go / narrow / change) and why
