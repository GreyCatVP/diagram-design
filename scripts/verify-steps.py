#!/usr/bin/env python3
"""Verify the structural claims of Steps diagrams.

Steps encodes order with one contiguous equal-width rail. Machine-readable
attributes bind every rail segment, printed number, and icon medallion to the
same stage so geometry cannot silently disagree with its labels.

Usage:
    python3 scripts/verify-steps.py --all
    python3 scripts/verify-steps.py skills/diagram-design/assets/example-steps.html
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"
RECT_RE = re.compile(r"<rect\b(?P<attrs>[^>]*)/?>", re.I)
CIRCLE_RE = re.compile(r"<circle\b(?P<attrs>[^>]*)/?>", re.I)
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>", re.I | re.S)
ATTR_RE = re.compile(r'''(?P<name>[\w:-]+)\s*=\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)')''')
TAG_STRIP_RE = re.compile(r"<[^>]+>")
TOLERANCE = 0.01


def attrs_of(raw: str) -> dict[str, str]:
    return {
        match.group("name").lower(): match.group("dq") if match.group("dq") is not None else match.group("sq")
        for match in ATTR_RE.finditer(raw)
    }


def number(attrs: dict[str, str], key: str) -> float | None:
    try:
        value = float(attrs[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def marks(source: str, role: str) -> list[tuple[str, dict[str, str], str]]:
    found: list[tuple[str, dict[str, str], str]] = []
    for tag, pattern in (("rect", RECT_RE), ("circle", CIRCLE_RE), ("text", TEXT_RE)):
        for match in pattern.finditer(source):
            attrs = attrs_of(match.group("attrs"))
            if attrs.get("data-role") != role:
                continue
            body = TAG_STRIP_RE.sub("", match.groupdict().get("body") or "").strip()
            found.append((tag, attrs, body))
    return found


def close(first: float | None, second: float | None) -> bool:
    return first is not None and second is not None and abs(first - second) <= TOLERANCE


def verify(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    errors: list[str] = []
    rails = marks(source, "rail")
    medallions = marks(source, "medallion")
    numbers = marks(source, "number")

    if not 3 <= len(rails) <= 7:
        errors.append(f"budget: expected 3..7 rail segments, found {len(rails)}")
        return errors

    by_index: dict[int, tuple[dict[str, str], str]] = {}
    for tag, attrs, _body in rails:
        if tag != "rect":
            errors.append("rail: data-role='rail' must be on a rect")
            continue
        step = attrs.get("data-step", "")
        try:
            index = int(attrs.get("data-index", ""))
        except ValueError:
            errors.append(f"rail: step {step!r} has a non-integer data-index")
            continue
        if index in by_index:
            errors.append(f"order: duplicate data-index {index}")
        by_index[index] = (attrs, step)
    expected_indices = list(range(1, len(rails) + 1))
    if sorted(by_index) != expected_indices:
        errors.append(f"order: data-index values must be {expected_indices}, found {sorted(by_index)}")
        return errors

    ordered = [by_index[index] for index in expected_indices]
    step_names = [step for _attrs, step in ordered]
    if any(not step for step in step_names) or len(step_names) != len(set(step_names)):
        errors.append("census: every rail segment needs one unique non-empty data-step")

    first = ordered[0][0]
    base_y, base_w, base_h = number(first, "y"), number(first, "width"), number(first, "height")
    if None in (base_y, base_w, base_h) or base_w <= 0 or base_h <= 0:
        errors.append("rail: x/y/width/height must be finite and positive")
        return errors
    previous_right: float | None = None
    centers: dict[str, float] = {}
    rail_center_y = base_y + base_h / 2
    for attrs, step in ordered:
        x, y, width, height = (number(attrs, key) for key in ("x", "y", "width", "height"))
        if None in (x, y, width, height):
            errors.append(f"rail: step {step!r} is missing finite geometry")
            continue
        if not close(y, base_y) or not close(width, base_w) or not close(height, base_h):
            errors.append(f"equal rail: step {step!r} does not share y, width, and height with its peers")
        if previous_right is not None and not close(x, previous_right):
            errors.append(f"contiguous rail: step {step!r} starts at {x:g}, expected {previous_right:g}")
        previous_right = x + width
        centers[step] = x + width / 2

    focal_rails = [attrs.get("data-step", "") for _tag, attrs, _ in rails if attrs.get("data-focal") == "true"]
    if len(focal_rails) != 1:
        errors.append(f"focal: expected exactly one focal rail segment, found {len(focal_rails)}")

    def one_per_step(items: list[tuple[str, dict[str, str], str]], role: str) -> dict[str, tuple[dict[str, str], str]]:
        result: dict[str, tuple[dict[str, str], str]] = {}
        for _tag, attrs, body in items:
            step = attrs.get("data-step", "")
            if step in result:
                errors.append(f"census: step {step!r} has more than one {role}")
            result[step] = (attrs, body)
        missing = sorted(set(step_names) - set(result))
        extra = sorted(set(result) - set(step_names))
        if missing or extra:
            errors.append(f"census: {role} steps differ from rail (missing={missing}, extra={extra})")
        return result

    medals = one_per_step(medallions, "medallion")
    labels = one_per_step(numbers, "number")
    radii: list[float] = []
    for step in step_names:
        if step in medals:
            attrs, _ = medals[step]
            cx, cy, radius = number(attrs, "cx"), number(attrs, "cy"), number(attrs, "r")
            if not close(cx, centers.get(step)) or not close(cy, rail_center_y):
                errors.append(f"medallion: step {step!r} is not centered on its rail segment")
            if radius is None or radius <= 0:
                errors.append(f"medallion: step {step!r} has an invalid radius")
            else:
                radii.append(radius)
        if step in labels:
            attrs, body = labels[step]
            index = step_names.index(step) + 1
            if body != f"{index:02d}":
                errors.append(f"number: step {step!r} prints {body!r}, expected {index:02d}")
            if not close(number(attrs, "x"), centers.get(step)):
                errors.append(f"number: step {step!r} is not centered on its rail segment")
    if radii and any(not close(radius, radii[0]) for radius in radii[1:]):
        errors.append("medallion: every stage must use the same radius")

    focal_medals = [attrs.get("data-step", "") for _tag, attrs, _ in medallions if attrs.get("data-focal") == "true"]
    if focal_rails and focal_medals != focal_rails:
        errors.append(f"focal: rail focal {focal_rails} and medallion focal {focal_medals} disagree")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    paths = sorted(ASSET_DIR.glob("example-steps*.html")) if args.all else args.paths
    if not paths:
        parser.error("pass one or more files, or --all")
    findings = 0
    for path in paths:
        errors = verify(path)
        if errors:
            findings += len(errors)
            print(f"FAIL {path}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"OK {path}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
