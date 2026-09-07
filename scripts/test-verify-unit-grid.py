#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-unit-grid.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_unit_grid", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def chart(cells: str, filled: int = 2) -> str:
    return (
        '<svg data-unit-grid="true" data-unit-total="100" data-unit-filled="' + str(filled)
        + '" data-unit-rows="10" data-unit-columns="10">'
        + f'<text data-unit-percent="true">{filled}%</text>'
        + f'<text data-unit-count="true">{filled} complete · {100 - filled} remaining</text>'
        + cells + '</svg>'
    )


def cell(index: int, state: str = "empty", width: int = 20) -> str:
    return (
        f'<rect data-unit-cell="{state}" data-unit-index="{index}" '
        f'x="{index % 10 * 24}" y="{index // 10 * 24}" width="{width}" height="20"/>'
    )


def main() -> int:
    verifier = load_verifier()
    valid_cells = "".join(cell(index, "filled" if index < 2 else "empty") for index in range(100))
    swapped_indices = (
        valid_cells.replace('data-unit-index="0"', 'data-unit-index="swap"', 1)
        .replace('data-unit-index="1"', 'data-unit-index="0"', 1)
        .replace('data-unit-index="swap"', 'data-unit-index="1"', 1)
    )
    out_of_order_fill = (
        valid_cells.replace('data-unit-cell="filled"', 'data-unit-cell="swap"', 1)
        .replace('data-unit-cell="empty"', 'data-unit-cell="filled"', 1)
        .replace('data-unit-cell="swap"', 'data-unit-cell="empty"', 1)
    )
    cases = [
        ("valid chart", chart(valid_cells), None),
        ("wrong filled count", chart(valid_cells, 3), "declares 3 filled units"),
        ("nonuniform cell", chart(valid_cells.replace('width="20"', 'width="24"', 1)), "identical dimensions"),
        ("duplicate index", chart(valid_cells.replace('data-unit-index="99"', 'data-unit-index="98"')), "indices"),
        ("missing cell", chart(valid_cells.rsplit("<rect", 1)[0]), "has 99 data-unit-cell"),
        ("overlapping cells", chart(valid_cells.replace(' x="24"', ' x="19"')), "must not overlap"),
        ("irregular gutter", chart(valid_cells.replace(' x="24"', ' x="25"')), "4px gutter"),
        ("indices out of reading order", chart(swapped_indices), "reading order"),
        ("filled cells out of reading order", chart(out_of_order_fill), "filled cells must occupy"),
    ]
    valid = chart(valid_cells)
    cases.extend([
        ("single quoted chart", valid.replace('"', "'"), None),
        ("wrong headline", valid.replace(">2%</text>", ">74%</text>"), "printed percentage"),
        ("wrong printed count", valid.replace("2 complete", "3 complete"), "printed count"),
        ("wrong remaining count", valid.replace("98 remaining", "97 remaining"), "printed count"),
        ("missing headline", valid.replace('data-unit-percent="true"', ''), "printed percentage"),
        ("missing count", valid.replace('data-unit-count="true"', ''), "printed count"),
        ("cell transform", valid.replace('<rect ', '<rect transform="translate(300 0)" ', 1), "transform"),
        ("inline transform", valid.replace('<rect ', '<rect style="transform:translateX(300px)" ', 1), "transform"),
        ("group transform", valid.replace('<rect ', '<g transform="translate(300 0)"><rect ', 1).replace('</svg>', '</g></svg>'), "transform"),
        ("root transform", valid.replace('<svg ', '<svg transform="translate(300 0)" ', 1), "transform"),
        ("CSS transform", '<style>rect { transform:translateX(300px); }</style>' + valid, "transform"),
        ("CSS translate", '<style>rect { translate:300px; }</style>' + valid, "translate"),
        ("group inline translate", valid.replace('<rect ', '<g style="translate:300px"><rect ', 1).replace('</svg>', '</g></svg>'), "translate"),
        ("inline rotate", valid.replace('<rect ', '<rect style="rotate:45deg" ', 1), "rotate"),
        ("inline scale", valid.replace('<rect ', '<rect style="scale:2" ', 1), "scale"),
        ("vendor transform", '<style>rect { -webkit-transform:translateX(300px); }</style>' + valid, "transform"),
        ("CSS position", '<style>rect { x:300px; }</style>' + valid, "CSS x"),
        ("CSS offset", '<style>rect { offset-path:path(\'M 0 0 L 300 0\'); }</style>' + valid, "offset-path"),
        ("CSS comment allowed", '<style>/* rect { transform:scale(2); } */</style>' + valid, None),
        ("HTML comment allowed", '<!-- <g transform="translate(300 0)"> -->' + valid, None),
        ("CSS text transform allowed", '<style>text { text-transform:uppercase; }</style>' + valid, None),
        ("single quoted transform", valid.replace('<rect ', "<rect transform='translate(300 0)' ", 1), "transform"),
    ])
    for filled in (0, 100):
        marks = "".join(cell(index, "filled" if index < filled else "empty") for index in range(100))
        cases.append((f"{filled} filled cells", chart(marks, filled), None))
    for path in sorted((ROOT / "skills/diagram-design/assets").glob("example-unit-grid*.html")):
        source = path.read_text(encoding="utf-8")
        cases.append((f"{path.name} valid", source, None))
        cases.append((f"{path.name} wrong headline", source.replace('>64%</text>', '>74%</text>'), "printed percentage"))
        cases.append((f"{path.name} moved cell", source.replace('<rect data-unit-cell=', '<rect transform="translate(300 0)" data-unit-cell=', 1), "transform"))
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as directory:
        for name, source, expected in cases:
            path = Path(directory) / "fixture.html"
            path.write_text(source, encoding="utf-8")
            findings = verifier.check(path)
            if expected is None and findings:
                failures.append(f"{name} failed: {findings}")
            elif expected is not None and not any(expected in finding for finding in findings):
                failures.append(f"{name} did not report {expected!r}: {findings}")
            else:
                print(f"OK: {name}")
    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
