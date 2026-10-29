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
| 7, 8 | Done | fastapi 0.162, uvicorn 0.54, httpx 0.28 installed; tests/test_server.py 3 passed. UI checklist 9/9 in headless Edge (Playwright, scratch venv, not a repo dependency); screenshots in `docs/screenshots/`. Two UI bugs found and fixed (see Failures) |
| 9 | Code done | scripts/smoke_llm.py and deploy/modal_glimmer.py compile. Not run |
| 6 (baseline) | Done | eval-20261029-090307-baseline-difficulty: 12/27 fixed (0.444) |
| 6 (Spark) | Done | smoke test plus 3 hard-fault runs, $0.106 |
| 10 (Spark 1.3) | Done | 27/27 fixed, $0.886. Second model deferred by the developer |
| 7 (API check) | Done | `np serve`: /api/topology 6 nodes and 13 flows, /api/catalog 9 classes, /api/profiles 4 (spark-1.3 key present), /api/scoreboard, /docs 200. Baseline run started over the API: events run_started, flows, run_finished, saved in order; a second start got 409; report served |

Full suite after Step 5: `NP_DOCKER=1 pytest` 126 passed (94 unit, 32 Docker).

Deviations:
- The Spark eval was interrupted after 7 runs when the previous session ended (machine restart; Docker stopped too). The 7 finished runs were kept and the other 20 ran as continuation evals with label p2-cont, so no scenario was paid for twice. Together the three eval ids cover each of the 27 variants exactly once.
- The plan file is `docs/phase_2.md`, not `docs/phase2-plan.md`.

## Difficulty gate (Step 6)
- Baseline eval id: eval-20261029-090307-baseline-difficulty
- Baseline fix rate (all 27): 0.444 (12/27)   Phase 1 classes: 12/12   New classes: 0/15
- Per class: route_missing 3/3, wrong_gateway 3/3, firewall_drop 3/3, interface_down 3/3, mtu_mismatch 0/3, wrong_nexthop 0/3, acl_typo 0/3, multi_fault 0/3 (s0 and s1 ended COMMITTED, partial fix, network still unhealthy), misleading_ticket 0/3. Errors 0, median 11.3 s per run
- Smoke test `scripts/smoke_llm.py --profile spark-1.3`: TOOL CALL yes, arguments parse as JSON, 2.1 s
- Spark hard-fault smoke runs (class, outcome, clean, diagnosis, cost):
  - mtu_mismatch s0: FIXED_VERIFIED, clean, diagnosis correct, $0.0415, 50.8 s, 1 plan. Found it with a 1400-byte don't-fragment ping and the r-core MTU; restored MTU 1500 and deleted the OUTPUT frag-needed DROP. Real cause found; nothing left behind
  - acl_typo s0: FIXED_VERIFIED, clean, diagnosis correct, $0.0233, 28.1 s, 1 plan. Spotted the ACCEPT pointing at 10.10.3.21; deleted it and re-appended the correct rule (same position, so no residual)
  - misleading_ticket s0 (ticket blames a dead file-server disk; real cause r-edge wrong next hop): FIXED_VERIFIED, clean, diagnosis correct, $0.0407, 48.7 s, 1 plan. Not misled: it tested flows that do not touch the file server first and recorded "disk failure would not break pc-staff->webserver" as evidence against the ticket's theory
  - Total for the three: $0.1055
- Human reference (fault, minutes, notes): not done yet (needs the developer with a stopwatch)
- Difficulty gate: passed. The baseline is at 0.444, below 0.80, and the new classes separate the model (15/15) from the runbook (0/15)

## Second model (Step 9)
- Baseten: credits status, model id that worked, tool calling yes/no
- Glimmer on Modal: deployed yes/no, tool calling yes/no, latency per call, GPU minutes used
- Glimmer decision and evidence:

## Phase 2 evaluation (Step 10)
| Agent / profile | Eval id | Runs | Fix rate | Clean fix rate | Diagnosis | Collateral | Gate | Median $ | Median s |
|---|---|---|---|---|---|---|---|---|---|
| baseline | eval-20261029-090307-baseline-difficulty | 27 | 0.444 | 0.444 | - | 0 | 0 | 0 | 11.3 |
| llm / spark-1.3 (effort low, prompt p2.0) | eval-20261029-093558-spark-1.3-p2 (7) + eval-20261029-094716-spark-1.3-p2-cont (2) + eval-20261029-094921-spark-1.3-p2-cont (18) | 27 | 1.0 | 0.889 | 1.0 | 0 | 0 | 0.0344 | 40.9 |

Spark 1.3 total cost for the 27 runs: $0.886. Errors: 0. Dev seeds 0-2, one repeat each: not for public quoting (Phase 3 runs held-out seeds with repeats).

By class (fixed): baseline route_missing 3/3, wrong_gateway 3/3, firewall_drop 3/3, interface_down 3/3, all five new classes 0/3. Spark 1.3 3/3 in every class.

Answers to the five questions:
1. Where the model beats the runbook: every new class. mtu_mismatch, wrong_nexthop, acl_typo, multi_fault and misleading_ticket are 3/3 for Spark and 0/3 for the baseline. On the Phase 1 classes both score 12/12.
2. Clean fix rate versus fix rate: 0.889 against 1.0. All three unclean runs fixed one half of the two-part MTU fault, and that half alone restores the flows: mtu_mismatch s0 and misleading_ticket s2 restored the MTU but left the OUTPUT frag-needed DROP on r-core, and multi_fault s2 deleted the DROP on r-edge but left eth2 at MTU 1100. The verifier passes these because traffic flows; only the residual metric shows the leftover. This is Phase 3 prompt or scoring work.
3. Collateral rollbacks in the eval: 0, so the eval has no verifier-rollback demo moment. A gate rejection did happen in a dashboard run (acl_typo s0, run 20261029-101435-spark-1.3-acl_typo-s0-r0: the first plan was blocked for missing rollback commands, and the resubmitted plan was committed). That is demo material.
4. misleading_ticket: 3/3 fixed with the correct diagnosis. In s0 the timeline shows it testing flows that do not touch the file server and rejecting the ticket's disk theory with evidence before acting.
5. Second model versus Spark 1.3: not measured yet. The developer deferred Step 9 (Baseten and Modal).

## Validation results (Step 11)
| ID | Criterion | Result | Pass? | Evidence |
|---|---|---|---|---|
| P2-V1 | 27 variants inject and heal | Docker suite 32/32 (27 fault variants plus 5 lab tests); validate-lab 27/27, reset median 3.7 s, max 3.8 s | yes | `NP_DOCKER=1 pytest` 126 passed; `np validate-lab --n 27` |
| P2-V2 | Gate cases and every reference plan pass | 31 dangerous rejected, 15 safe allowed, every catalog fix and bad fix passes | yes | `tests/test_gate.py` 48 passed |
| P2-V3 | Reference fixes clean; bad fixes roll back identically | 27/27 and 21/21 | yes | `np validate-verifier` (run twice, 29 Oct) |
| P2-V4 | Baseline below 0.80 on the 27-variant set | 0.444 | yes | eval-20261029-090307-baseline-difficulty |
| P2-V5 | Scoreboard with Spark 1.3 plus a second model | Spark 1.3 row done (27 runs); second model not run | **pending** | Deferred by the developer until Step 9 |
| P2-V6 | Dashboard shows a full live run | 9/9 checklist items, checked in headless Edge | yes | `docs/screenshots/`; run 20261029-101435-spark-1.3-acl_typo-s0-r0 |
| P2-V7 | Glimmer decision recorded with evidence | not attempted yet | **pending** | Step 9 deferred |
| P2-V8 | Every run produces a report | 64 reports, 64 DB rows (after the final screenshot run) | yes | `reports/` count vs `select count(*) from runs` |

Stability: five `np check` in a row, all HEALTHY. Full suite: 126 passed (94 unit, 32 Docker).

## Failures worth remembering
- Dashboard bug: the changed-flow highlight was cleared when the final `flows` event redrew the table. Fixed in web/app.js by keeping the last plan's changed set for the final render.
- Dashboard bug: the Scoreboard panel also showed under the Run view, because `#view-score { display: block; }` overrode the `hidden` attribute. Fixed with a global `[hidden] { display: none !important; }` in web/style.css.
- The pre-commit hook flagged docs that quote the key pattern (the plan doc and these notes). The plan doc is excluded from the scan; the notes were reworded instead.
- Previous session ended mid-eval, which also stopped Docker. Resumed without re-running finished scenarios.

## Decision (go / narrow / change) and why
Not taken yet; Phase 2 stays open. Six of eight criteria pass. P2-V5 and P2-V7 wait for Step 9 (second model, Glimmer decision), which the developer deferred, and the human reference timing is still to do.

Interim read of the evidence (for the developer to accept or change): the benchmark now separates the model from the runbook (new classes 15/15 against 0/15) and the safety core is still exact on the larger catalog. The weak spot is clean-fix discipline on two-part MTU faults (3 of 27 runs left half the fault in place). That points to Go for Phase 3 once Step 9 is done, with MTU clean-fix work at the top of the list.
