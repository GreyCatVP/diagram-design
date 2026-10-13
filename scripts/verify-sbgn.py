#!/usr/bin/env python3
"""Verify the SBGN process-description HTML contract using only the stdlib.

Checks unique IDs, arc kinds, bipartite species/process arcs, compartment
containment, glyph kinds, and the Bruno ceiling. Containment reads x, y, width
and height, so a transform or positional CSS on a glyph, its bounds or an
ancestor group inside the map is a finding. Files without data-diagram="sbgn" are
skipped. This verifies authored declarations, not whether they describe an
external SBML model.

Usage: python3 scripts/verify-sbgn.py [--all | FILE ...]
No arguments and --all check every shipped SBGN example.
Exit: 0 clean, 1 contract findings, 2 unreadable input/usage.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
NUMBER_RE = re.compile(NUMBER)
ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]*\Z")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
DIAGRAM = "sbgn"
GLYPH_KINDS = {"macromolecule", "process", "compartment", "source-sink"}
ARC_KINDS = {"consumption", "production", "reversible", "modulation"}
ARC_LIST = ", ".join(sorted(ARC_KINDS))
GLYPH_LIST = ", ".join(sorted(GLYPH_KINDS))
SPECIES = {"macromolecule", "source-sink"}
MAX_MACRO = 7
MAX_PROCESS = 6
MAX_COMPARTMENT = 1
MAX_SOURCE = 2
GRID = 4.0
EPS = 1e-6
MAX_COORDINATE = 1e7
# CSS properties that move or resize an SVG element away from the x, y,
# width and height attributes the containment check reads.
POSITION_PROPERTIES = {
    "transform", "translate", "rotate", "scale", "x", "y", "width", "height",
    "offset", "offset-path", "offset-distance", "offset-position", "offset-anchor", "offset-rotate",
}
# Element names a stylesheet selector can use to reach a glyph or its group.
# The root <svg> is left out: sizing it scales the whole map uniformly.
SVG_MARK_TAGS = {
    "a", "circle", "defs", "ellipse", "foreignobject", "g", "image", "line", "marker", "path",
    "pattern", "polygon", "polyline", "rect", "switch", "symbol", "text", "textpath", "tspan", "use",
}
CSS_ESCAPE_RE = re.compile(r"\\([0-9a-fA-F]{1,6})[ \t\r\n\f]?|\\(.)", re.DOTALL)
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_BLOCK_RE = re.compile(r"([^{}]*)\{([^{}]*)\}")


@dataclass(eq=False)
class Node:
    tag: str
    attrs: dict[str, str]
    line: int
    parent: Node | None = None
    children: list[Node] = field(default_factory=list)
    duplicates: set[str] = field(default_factory=set)

    def ancestors(self):
        current = self.parent
        while current is not None:
            yield current
            current = current.parent


class Scanner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {}, 1)
        self.stack = [self.root]
        self.nodes: list[Node] = []
        self.errors: list[str] = []
        self.stylesheets: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):
        values = {}
        duplicates = set()
        for name, value in attrs:
            if name in values:
                duplicates.add(name)
            values.setdefault(name, value or "")
        node = Node(tag, values, self.getpos()[0], self.stack[-1], duplicates=duplicates)
        self.stack[-1].children.append(node)
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        indexes = [i for i, node in enumerate(self.stack) if node.tag == tag]
        in_svg = any(node.tag == "svg" for node in self.stack)
        if not indexes:
            if in_svg:
                self.errors.append(f"line {self.getpos()[0]}: malformed SVG closing tag {tag}")
            return
        index = indexes[-1]
        if in_svg and index != len(self.stack) - 1:
            self.errors.append(f"line {self.getpos()[0]}: malformed SVG nesting at {tag}")
        del self.stack[index:]

    def handle_data(self, data):
        if self.stack[-1].tag == "style":
            self.stylesheets.append((self.getpos()[0], data))

    def finish(self, source):
        self.feed(source)
        self.close()
        if any(node.tag == "svg" for node in self.stack):
            self.errors.append("unclosed SVG")


@dataclass
class Box:
    node: Node
    identity: str
    kind: str
    x: float
    y: float
    w: float
    h: float
    compartment: str | None = None

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


def number(raw: str) -> float:
    if not NUMBER_RE.fullmatch(raw.strip()):
        raise ValueError("missing, malformed or non-finite number")
    value = float(raw)
    if not math.isfinite(value) or abs(value) > MAX_COORDINATE:
        raise ValueError("number must be finite and within 10,000,000 units")
    return value


def on_grid(value: float) -> bool:
    ratio = value / GRID
    return math.isfinite(ratio) and abs(ratio - round(ratio)) <= EPS


def identity_ok(raw: str) -> bool:
    return bool(raw) and ID_RE.fullmatch(raw) is not None


def within_box(inner: Box, outer: Box) -> bool:
    return (inner.x + EPS >= outer.x and inner.y + EPS >= outer.y
            and inner.right <= outer.right + EPS and inner.bottom <= outer.bottom + EPS)


def parse_bounds(carrier: Node) -> tuple[float, float, float, float]:
    bounds = [child for child in carrier.children if child.attrs.get("data-role") == "bounds"]
    target = bounds[0] if len(bounds) == 1 else carrier
    if carrier.attrs.get("data-role") == "bounds":
        target = carrier
    elif len(bounds) != 1 and carrier.tag != "rect":
        raise ValueError("glyph must expose exactly one data-role=\"bounds\" rect")
    attrs = target.attrs
    x = number(attrs.get("x", ""))
    y = number(attrs.get("y", ""))
    w = number(attrs.get("width", ""))
    h = number(attrs.get("height", ""))
    if w <= 0 or h <= 0:
        raise ValueError("bounds width and height must be positive")
    return x, y, w, h


def _split_top_level(text: str, separators: str) -> list[str]:
    """Split at separators outside quotes, brackets and parentheses."""
    parts, current, depth, quote, index = [], [], 0, "", 0
    while index < len(text):
        char = text[index]
        escape = CSS_ESCAPE_RE.match(text, index) if char == "\\" else None
        if escape:
            # A hex escape may swallow one whitespace; it is not a combinator.
            current.append(escape.group(0))
            index = escape.end()
            continue
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        elif depth == 0 and char in separators:
            parts.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


def _css_unescape(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        if match.group(1):
            code = int(match.group(1), 16)
            return chr(code) if 0 < code <= 0x10FFFF else "\ufffd"
        return match.group(2)
    return CSS_ESCAPE_RE.sub(replace, text)


def positional_properties(declarations: str) -> list[str]:
    """CSS property names in a declaration block that can move an element."""
    found = []
    for declaration in _split_top_level(CSS_COMMENT_RE.sub("", declarations), ";"):
        name, colon, _value = declaration.partition(":")
        name = _css_unescape(name).strip().lower()
        if colon and name in POSITION_PROPERTIES:
            found.append(name)
    return found


def _without_groups(compound: str) -> str:
    """Drop attribute-selector and functional-pseudo contents, quotes included."""
    out, depth, quote, index = [], 0, "", 0
    while index < len(compound):
        char = compound[index]
        escape = CSS_ESCAPE_RE.match(compound, index) if char == "\\" else None
        if escape:
            if depth == 0:
                out.append(escape.group(0))
            index = escape.end()
            continue
        if quote:
            if char == quote:
                quote = ""
        elif depth and char in "\"'":
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(char)
        index += 1
    return "".join(out)


def selector_can_reach_marks(selector: str, svg_names: set[str]) -> bool:
    """False only when the selector's subject is provably page chrome.

    The subject (last compound) can be a glyph when it names an SVG mark
    element, uses an attribute selector or functional pseudo-class without
    naming an HTML element, or carries a class or id that an element inside
    the diagram also carries. Anything unclear counts as able to reach.
    """
    compounds = [part for part in _split_top_level(selector, " \t\r\n\f>+~") if part.strip()]
    if not compounds:
        return False
    compound = compounds[-1].strip()
    bare = _css_unescape(_without_groups(compound))
    element = re.match(r"(?:(?:[A-Za-z_][\w-]*|\*)?\|)?([A-Za-z][\w-]*|\*)?", bare)
    tag = (element.group(1) or "").lower() if element else ""
    if tag and tag != "*":
        # An HTML element, or the root <svg>, cannot be a glyph or its group.
        return tag in SVG_MARK_TAGS
    if "[" in compound or "(" in compound:
        return True
    names = set(re.findall(r"[.#]([\w-]+)", bare))
    if not names:
        return True
    return bool(names & svg_names)


def looks_like_sbgn(source: str) -> bool:
    scanner = Scanner()
    scanner.finish(source)
    return any(node.tag == "svg" and node.attrs.get("data-diagram") == DIAGRAM
               for node in scanner.nodes)


def check_source(path: Path, source: str) -> list[str]:
    scanner = Scanner()
    scanner.finish(source)
    findings: list[str] = []
    roots = [node for node in scanner.nodes
             if node.tag == "svg" and node.attrs.get("data-diagram") == DIAGRAM]
    if not roots:
        return []

    def fail(node: Node, message: str) -> None:
        findings.append(f"{path.name}:{node.line}: {message}")

    if len(roots) != 1:
        fail(roots[0], 'require exactly one svg data-diagram="sbgn"')
        return findings
    root = roots[0]
    findings.extend(f"{path.name}: {error}" for error in scanner.errors)
    for node in scanner.nodes:
        if node is root or root in node.ancestors():
            if node.duplicates:
                fail(node, f"duplicate attributes: {', '.join(sorted(node.duplicates))}")

    glyphs: dict[str, Box] = {}
    ids: dict[str, Node] = {}

    def register(identity: str, carrier: Node) -> bool:
        if not identity_ok(identity):
            fail(carrier, "identity must be a single XML Name starting with a letter")
            return False
        if identity in ids:
            fail(carrier, f'duplicate ID "{identity}"')
            return False
        ids[identity] = carrier
        return True

    def identity_for(kind: str, attrs: dict[str, str]) -> str:
        if kind == "macromolecule" or kind == "source-sink":
            return attrs.get("data-entity-id", "")
        if kind == "process":
            return attrs.get("data-process-id", "")
        return attrs.get("data-compartment-id", "")

    position_checked: set[int] = set()

    def check_position(node: Node, identity: str, role: str) -> None:
        """Containment reads x/y/width/height; nothing may move the drawn glyph."""
        if id(node) in position_checked:
            return
        position_checked.add(id(node))
        where = f'{role} <{node.tag}> of glyph "{identity}"'
        if "transform" in node.attrs:
            fail(node, f"{where} has a transform attribute; place glyphs with x, y, width and height only")
        moved = positional_properties(node.attrs.get("style", ""))
        if moved:
            fail(node, f"{where} has a positional inline style ({', '.join(moved)}); "
                       "place glyphs with x, y, width and height only")
        if role == "ancestor" and node.tag in {"svg", "symbol"}:
            fail(node, f'glyph "{identity}" sits inside a nested <{node.tag}>, which offsets and scales it')

    for node in scanner.nodes:
        if node is not root and root not in node.ancestors():
            continue
        kind = node.attrs.get("data-kind", "")
        if kind in GLYPH_KINDS:
            identity = identity_for(kind, node.attrs)
            if not register(identity, node):
                continue
            check_position(node, identity, "glyph")
            for child in node.children:
                if child.attrs.get("data-role") == "bounds":
                    check_position(child, identity, "bounds")
            for ancestor in node.ancestors():
                if ancestor is root:
                    break
                check_position(ancestor, identity, "ancestor")
            try:
                x, y, w, h = parse_bounds(node)
            except ValueError as error:
                fail(node, str(error))
                continue
            if kind != "source-sink":
                for value in (x, y, w, h):
                    if not on_grid(value):
                        fail(node, "glyph bounds must sit on the 4px grid")
                        break
            compartment = node.attrs.get("data-compartment") or None
            glyphs[identity] = Box(node, identity, kind, x, y, w, h, compartment)

    macros = [g for g in glyphs.values() if g.kind == "macromolecule"]
    processes = [g for g in glyphs.values() if g.kind == "process"]
    compartments = [g for g in glyphs.values() if g.kind == "compartment"]
    sources = [g for g in glyphs.values() if g.kind == "source-sink"]
    if not macros:
        fail(root, "SBGN requires at least one macromolecule")
    if not processes:
        fail(root, "SBGN requires at least one process")
    if not compartments:
        fail(root, "SBGN requires at least one compartment")
    if len(macros) > MAX_MACRO:
        fail(root, "macromolecule budget is 7")
    if len(processes) > MAX_PROCESS:
        fail(root, "process budget is 6")
    if len(compartments) > MAX_COMPARTMENT:
        fail(root, "compartment budget is 1")
    if len(sources) > MAX_SOURCE:
        fail(root, "source-sink budget is 2")

    svg_names: set[str] = set()
    for node in scanner.nodes:
        if root in node.ancestors():
            svg_names.update(node.attrs.get("class", "").split())
            if node.attrs.get("id"):
                svg_names.add(node.attrs["id"])
    for line, sheet in scanner.stylesheets:
        sheet = CSS_COMMENT_RE.sub(lambda match: "\n" * match.group(0).count("\n"), sheet)
        for match in CSS_BLOCK_RE.finditer(sheet):
            moved = positional_properties(match.group(2))
            if not moved:
                continue
            selectors = [selector.strip() for selector in _split_top_level(match.group(1), ",")]
            reaching = [selector for selector in selectors
                        if selector and selector_can_reach_marks(selector, svg_names)]
            if reaching:
                at = line + sheet[:match.start(2)].count("\n")
                findings.append(
                    f"{path.name}:{at}: stylesheet rule {', '.join(reaching)!r} sets {', '.join(moved)} "
                    "on elements the diagram's glyphs can match; place glyphs with x, y, width and height only")

    compartment_ids = {g.identity for g in compartments}
    for box in glyphs.values():
        if box.kind in {"macromolecule", "process", "source-sink"}:
            if not box.compartment or box.compartment not in compartment_ids:
                fail(box.node, "data-compartment must name a compartment in this file")
                continue
            parent = glyphs[box.compartment]
            if not within_box(box, parent):
                fail(box.node, f'glyph "{box.identity}" is not geometrically inside compartment "{box.compartment}"')

    species = {g.identity for g in glyphs.values() if g.kind in SPECIES}
    process_ids = {g.identity for g in processes}

    for node in scanner.nodes:
        if node is not root and root not in node.ancestors():
            continue
        kind = node.attrs.get("data-kind", "")
        is_arc = "data-from" in node.attrs or "data-to" in node.attrs
        if kind not in ARC_KINDS:
            # An unknown kind must fail here: skipping it would also skip the
            # endpoint checks, so a typo would pass a species-to-species arc.
            if is_arc and not kind:
                fail(node, f"arc data-kind is missing; use one of {ARC_LIST}")
            elif is_arc:
                fail(node, f'arc data-kind "{kind}" must be one of {ARC_LIST}')
            elif "data-kind" in node.attrs and kind not in GLYPH_KINDS:
                fail(node, f'unknown data-kind "{kind}"; glyphs use {GLYPH_LIST}, arcs use {ARC_LIST}')
            continue
        source = node.attrs.get("data-from", "")
        target = node.attrs.get("data-to", "")
        if not identity_ok(source) or not identity_ok(target):
            fail(node, "arc data-from and data-to must be single XML Names")
            continue
        if kind == "consumption":
            if source not in species or target not in process_ids:
                fail(node, "consumption must run species → process")
        elif kind == "production":
            if source not in process_ids or target not in species:
                fail(node, "production must run process → species")
        elif kind == "modulation":
            if source not in species or target not in process_ids:
                fail(node, "modulation must run species → process")
        elif kind == "reversible":
            pair = {source, target}
            if not (pair & species and pair & process_ids):
                fail(node, "reversible must join a species and a process")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument("--all", action="store_true", help="check every shipped SBGN example")
    args = parser.parse_args()
    if args.all and args.paths:
        parser.error("use --all or explicit paths, not both")
    targets = sorted(ASSET_DIR.glob("example-*.html")) if args.all or not args.paths else [Path(value) for value in args.paths]
    checked, findings = 0, []
    for path in targets:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            print(f"error: cannot read {path}: {error}", file=sys.stderr)
            return 2
        if not looks_like_sbgn(source):
            continue
        checked += 1
        findings.extend(check_source(path, source))
    if not checked:
        print("error: no SBGN diagrams found", file=sys.stderr)
        return 1
    for finding in findings:
        print(finding)
    if findings:
        print(f"{len(findings)} SBGN finding(s) across {checked} file(s).")
        return 1
    print(f"OK SBGN: {checked} file(s); IDs, bipartite arcs, compartments and budget agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
