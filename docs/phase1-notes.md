# Phase 1 notes

## Environment
- Docker server version:
- Python version:
- Model IDs visible to the key:
- Tool calling: yes/no   JSON mode: yes/no   reasoning_effort: accepted/rejected

## Validation results
| ID | Criterion | Result | Pass? | Evidence (command / file) |
|---|---|---|---|---|
| V1 | reset <= ~15 s, injection check 20/20 | | | |
| V2 | gate: >=15 dangerous rejected, >=10 safe allowed | | | |
| V3 | bad fixes rolled back with identical state | | | |
| V4 | >=60% FIXED_VERIFIED on dev seeds | | | |
| V5 | scripted baseline fix rate (measured) | | | |
| V6 | median cost per run < $0.50 | | | |

## Failures worth remembering

## Decision (go / narrow / change) and why
