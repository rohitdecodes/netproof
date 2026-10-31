"""Claims check for public text (README, submission copy).

Fails when the text contains:
  - wording the project does not use in public (production-ready, 100%, guarantees, human speed claims)
  - unfilled placeholders (TODO, TBD, <fill ...>, {{ ... }})
  - emoji
  - links to local-only files (docs/phase*.md) or to relative paths that do not exist
  - a fraction k/n that does not appear in the results file (when --results is given)
A line containing <!-- claims:ok --> is skipped (for example verifier totals, which are not benchmark results).

Usage: python scripts/check_claims.py README.md [--results docs/results.md]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FORBIDDEN = [
    r"production[- ]ready", r"\b100\s?%", r"state[- ]of[- ]the[- ]art", r"\bguarantee", r"faster than (a )?humans?",
    r"\bbulletproof\b", r"\bunbreakable\b", r"\bnever fails\b",
    r"\bTODO\b", r"\bTBD\b", r"<fill", r"\{\{",          # unfilled template placeholders
]
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")
LINK = re.compile(r"\]\(([^)\s]+)\)")
FRACTION = re.compile(r"(?<![\d./])(\d+)/(\d+)(?![\d./])")
SKIP = "<!-- claims:ok -->"


def check(text: str, base: Path, results: str | None = None) -> list:
    problems = []
    in_code = False
    for no, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or SKIP in line:
            continue
        for pat in FORBIDDEN:
            if re.search(pat, line, re.IGNORECASE):
                problems.append(f"line {no}: forbidden wording /{pat}/: {line.strip()[:100]}")
        if EMOJI.search(line):
            problems.append(f"line {no}: emoji")
        for target in LINK.findall(line):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path = target.split("#", 1)[0]
            if re.search(r"(^|/)docs/phase", path):
                problems.append(f"line {no}: link to a local-only plan file: {target}")
            elif path and not (base / path).exists():
                problems.append(f"line {no}: link target does not exist: {target}")
        if results is not None:
            for k, n in FRACTION.findall(line):
                if f"{k}/{n}" not in results:
                    problems.append(f"line {no}: {k}/{n} is not in the results file")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--results", default=None)
    a = ap.parse_args(argv)
    results = Path(a.results).read_text(encoding="utf-8") if a.results else None
    total = 0
    for f in a.files:
        p = Path(f)
        probs = check(p.read_text(encoding="utf-8"), p.parent, results)
        for pr in probs:
            print(f"{f}: {pr}")
        total += len(probs)
    print("CLAIMS CHECK PASSED" if total == 0 else f"CLAIMS CHECK FAILED: {total} problem(s)")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
