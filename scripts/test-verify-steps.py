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


def stage_fixture(count: int, stage_width: int | None = None) -> str:
    """Build a minimal legal fixture from the documented 1280px formula."""
    usable = 1280 - 2 * 80
    width = stage_width or min(224, 4 * (usable // (4 * count)))
    start = (1280 - count * width) / 2
    parts = ['<svg viewBox="0 0 1280 720">', '<g aria-hidden="true">']
    for index in range(1, count + 1):
        x = start + (index - 1) * width
        focal = ' data-focal="true"' if index == 3 else ""
        parts.append(f'<rect x="{x:g}" y="240" width="{width:g}" height="48" data-role="rail" data-step="s{index}" data-index="{index}"{focal}/>')
    parts.append('</g>')
    for index in range(1, count + 1):
        cx = start + (index - 0.5) * width
        focal = ' data-focal="true"' if index == 3 else ""
        parts.append(f'<circle cx="{cx:g}" cy="264" r="36" data-role="medallion" data-step="s{index}"{focal}/>')
        parts.append(f'<text x="{cx:g}" y="164" data-role="number" data-step="s{index}">{index:02d}</text>')
    parts.append('</svg>')
    return "".join(parts)


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
        for count in (6, 7):
            path = directory / f"good-{count}.html"
            path.write_text(stage_fixture(count), encoding="utf-8")
            code, output = run(path)
            if code:
                failures.append(f"documented {count}-stage fixture failed\n{output}")
            else:
                print(f"OK: documented {count}-stage fixture passes")
        clipped = directory / "bad-clipped-seven.html"
        clipped.write_text(stage_fixture(7, stage_width=224), encoding="utf-8")
        code, output = run(clipped)
        if code == 0 or "outside the viewBox" not in output:
            failures.append(f"old clipped seven-stage formula was not rejected\n{output}")
        else:
            print("OK: old clipped seven-stage formula rejected")
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
        old = 'data-role="medallion" data-step="decide"'
        new = 'data-role="medallion" data-step="research"'
        path = directory / "bad-duplicate-and-missing-medallion.html"
        if source.count(old) != 1:
            failures.append(f"fixture duplicate and missing medallion anchor occurs {source.count(old)} times")
        else:
            path.write_text(source.replace(old, new, 1), encoding="utf-8")
            code, output = run(path)
            mismatch = "census: medallion steps differ from rail"
            duplicate = "census: step 'research' has more than one medallion"
            if code == 0 or mismatch not in output or duplicate not in output:
                failures.append(f"duplicate and missing medallion: expected both census findings\n{output}")
            elif output.index(mismatch) > output.index(duplicate):
                failures.append(f"duplicate and missing medallion: expected missing/extra finding first\n{output}")
            else:
                print("OK: duplicate and missing medallion reports the full census first")
        transform_cases = (
            ("rail transform", 'data-role="rail"', 'transform="translate(16 0)" data-role="rail"'),
            ("rail ancestor transform", '<g aria-hidden="true">', '<g aria-hidden="true" transform="translate(16 0)">'),
            ("rail CSS transform", '</head>', '<style>[data-role="rail"] { transform: translateX(16px); }</style></head>'),
        )
        for index, (name, old, new) in enumerate(transform_cases, len(cases)):
            if source.count(old) < 1:
                failures.append(f"fixture {name!r} anchor is missing")
                continue
            path = directory / f"bad-{index}.html"
            path.write_text(source.replace(old, new, 1), encoding="utf-8")
            code, output = run(path)
            if code == 0 or "transform:" not in output:
                failures.append(f"{name}: expected transform rejection\n{output}")
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
