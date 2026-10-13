#!/usr/bin/env python3
"""Quoted CSS data is not a geometry declaration, in every verifier that scans for one.

Eleven verifiers refuse a CSS declaration that can move a verified mark. Each read
`body { --notes: "literal;transform:translate(999px)" }` as a `transform`
declaration, although the browser reads a quoted string that moves nothing (#431).

Both polarities, on a shipped example of each type: quoted data passes, and a live
declaration still fails when a quote, a comment, an escape or a url() stands near
it in a way that could make a careless string reader skip it.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

TYPES = ("architecture-delta", "beeswarm", "bump", "bubble", "marimekko", "ridgeline",
         "service-blueprint", "polar", "streamgraph", "slopegraph", "waterfall")

# (label, passes, CSS added at the top of the first <style>)
CASES = (
    ("double-quoted data", True, 'body { --notes: "literal;transform:translate(999px)" }'),
    ("single-quoted data", True, "body { --notes: 'literal;transform:translate(999px)' }"),
    ("a live transform", False, "rect { transform: translate(999px) }"),
    ("a live transform after a string", False, 'body { --a: "x" } rect { transform: translate(999px) }'),
    # The string holds `/*`: a reader that strips comments first hides the transform.
    ("a comment opener inside a string", False, 'rect { --a: "/*"; transform: translate(9px); --b: "*/" }'),
    ("a quote inside a comment", False, '/* " */ rect { transform: translate(9px) } /* " */'),
    # `\"` is an escaped character, not the start of a string.
    ("an escaped quote", False, 'rect { --a: \\"; transform: translate(9px); --b: "x" }'),
    # A quote in an unquoted url() does not open a string either.
    ("a quote in an unquoted url()", False, 'rect { background: url(a"b); transform: translate(9px); --x: "c" }'),
    # An escaped `)` does not end the url(), so the quote after it is still inside it.
    ("a quote after an escaped paren in url()", False,
     'rect { background: url(a\\)"b); transform: translate(9px); --x: "c" }'),
    # A form feed ends a string just as a line feed does.
    ("a form feed inside a string", False, 'rect { --a: "\f;transform:translate(9px);--b:" }'),
    # A string ends at its line: the next rule is live.
    ("an unterminated string", False, 'body { --a: "x;\n} rect { transform: translate(9px) } body { --b: "y" }'),
)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        for kind in TYPES:
            example = sorted(ASSET_DIR.glob(f"example-{kind}*.html"))[0]
            source = example.read_text(encoding="utf-8")
            for number, (label, passes, css) in enumerate(CASES):
                page = Path(scratch) / f"{kind}-{number}.html"
                page.write_text(
                    re.sub(r"(<style[^>]*>)", lambda found: found.group(1) + "\n" + css + "\n", source, count=1),
                    encoding="utf-8",
                )
                result = subprocess.run(
                    [sys.executable, str(ROOT / f"scripts/verify-{kind}.py"), str(page)],
                    capture_output=True, text=True, check=False,
                )
                if (result.returncode == 0) != passes:
                    failures.append(f"{kind}: {label} should {'pass' if passes else 'fail'}")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print(f"OK CSS string scan: {len(TYPES)} verifier(s), {len(CASES)} case(s) each, both polarities")
    return 0


if __name__ == "__main__":
    sys.exit(main())
