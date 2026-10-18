#!/usr/bin/env python3
"""Adversarial tests for verify-steps.py."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-steps.py"
GOOD = ROOT / "skills/diagram-design/assets/example-steps.html"


def run(path: Path) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def main() -> int:
    source = GOOD.read_text(encoding="utf-8")
    failures: list[str] = []
    for path in sorted(GOOD.parent.glob("example-steps*.html")):
        code, output = run(path)
        if code:
            failures.append(f"shipped {path.name} failed\n{output}")
        else:
            print(f"OK: shipped {path.name} passes")

    cases = (
        ("gap in the rail", 'x="304" y="240" width="224"', 'x="312" y="240" width="224"', "contiguous rail"),
        ("one segment is wider", 'x="304" y="240" width="224"', 'x="304" y="240" width="232"', "equal rail"),
        ("duplicate stage index", 'data-step="research" data-index="2"', 'data-step="research" data-index="3"', "data-index"),
        ("focal rail removed", 'data-index="3" data-focal="true"', 'data-index="3"', "exactly one focal"),
        ("medallion shifted off center", 'cx="416" cy="264" r="36" stroke="#2d3142" data-role="medallion"', 'cx="424" cy="264" r="36" stroke="#2d3142" data-role="medallion"', "not centered"),
        ("printed number disagrees", 'data-role="number" data-step="research">02</text>', 'data-role="number" data-step="research">20</text>', "prints '20'"),
    )
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        for index, (name, old, new, expected) in enumerate(cases):
            if source.count(old) != 1:
                failures.append(f"fixture {name!r} anchor occurs {source.count(old)} times")
                continue
            path = directory / f"bad-{index}.html"
            path.write_text(source.replace(old, new, 1), encoding="utf-8")
            code, output = run(path)
            if code == 0 or expected not in output:
                failures.append(f"{name}: expected rejection containing {expected!r}\n{output}")
            else:
                print(f"OK: {name} rejected")
    if failures:
        print("FAIL steps verifier tests")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All Steps verifier tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
