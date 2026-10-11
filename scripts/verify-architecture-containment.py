#!/usr/bin/env python3
"""Verify the Architecture containment HTML contract using only the stdlib.

Checks unique IDs, resolving parents, no cycles, geometric containment,
admin-band vs traffic-box shapes, PaaS placement, endpoint targets, declared
peerings, sibling axes, and the 4px grid. Files without
data-grammar="architecture-containment" are skipped. This verifies authored
declarations, not whether they describe an external system.

Usage: python3 scripts/verify-architecture-containment.py [--all | FILE ...]
No arguments and --all check every shipped architecture-containment example.
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
GRAMMAR = "architecture-containment"
SCOPE_KINDS = {"admin", "traffic"}
NODE_KINDS = {"compute", "endpoint", "managed"}
ADMIN_RX = 4.0
TRAFFIC_RX = 8.0
GRID = 4.0
EPS = 1e-6
MAX_COORDINATE = 1e7
MAX_ADMIN = 2
MAX_TRAFFIC = 4
MAX_NODES = 8


@dataclass(eq=False)
class Node:
    tag: str
    attrs: dict[str, str]
    line: int
    parent: Node | None = None
    children: list[Node] = field(default_factory=list)
    content: list[str | Node] = field(default_factory=list)
    duplicates: set[str] = field(default_factory=set)

    def ancestors(self):
        parent = self.parent
        while parent is not None:
            yield parent
            parent = parent.parent


class Scanner(HTMLParser):
    """HTML parsing honors unquoted attrs, entities, comments and raw style text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {}, 1)
        self.stack = [self.root]
        self.nodes: list[Node] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = {}
        duplicates = set()
        for name, value in attrs:
            if name in values:
                duplicates.add(name)
            values.setdefault(name, value or "")
        node = Node(tag, values, self.getpos()[0], self.stack[-1], duplicates=duplicates)
        self.stack[-1].children.append(node)
        self.stack[-1].content.append(node)
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
        self.stack[-1].content.append(data)

    def finish(self, source):
        self.feed(source)
        self.close()
        if any(node.tag == "svg" for node in self.stack):
            self.errors.append("unclosed SVG")


@dataclass
class Box:
    node: Node
    identity: str
    x: float
    y: float
    w: float
    h: float
    rx: float | None
    dashed: bool
    kind: str
    parent_id: str | None
    target: str | None = None

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


def within_box(inner: Box, outer: Box) -> bool:
    return (inner.x + EPS >= outer.x and inner.y + EPS >= outer.y
            and inner.right <= outer.right + EPS and inner.bottom <= outer.bottom + EPS)


def overlaps(a: Box, b: Box) -> bool:
    return (a.x < b.right - EPS and a.right > b.x + EPS
            and a.y < b.bottom - EPS and a.bottom > b.y + EPS)


def identity_ok(raw: str) -> bool:
    return bool(raw) and ID_RE.fullmatch(raw) is not None


def parse_box(node: Node, identity: str, kind: str, parent_id: str | None, target: str | None = None) -> Box:
    attrs = node.attrs
    x = number(attrs.get("x", ""))
    y = number(attrs.get("y", ""))
    w = number(attrs.get("width", ""))
    h = number(attrs.get("height", ""))
    rx_raw = attrs.get("rx")
    rx = number(rx_raw) if rx_raw not in (None, "") else None
    dashed = bool(attrs.get("stroke-dasharray", "").strip())
    if w <= 0 or h <= 0:
        raise ValueError("bounds width and height must be positive")
    return Box(node, identity, x, y, w, h, rx, dashed, kind, parent_id, target)


def looks_like_containment(source: str) -> bool:
    scanner = Scanner()
    scanner.finish(source)
    return any(node.tag == "svg" and node.attrs.get("data-grammar") == GRAMMAR
               for node in scanner.nodes)


def check_source(path: Path, source: str) -> list[str]:
    scanner = Scanner()
    scanner.finish(source)
    findings: list[str] = []
    roots = [node for node in scanner.nodes
             if node.tag == "svg" and node.attrs.get("data-grammar") == GRAMMAR]
    if not roots:
        return []

    def fail(node: Node, message: str) -> None:
        findings.append(f"{path.name}:{node.line}: {message}")

    if len(roots) != 1:
        fail(roots[0], 'require exactly one svg data-grammar="architecture-containment"')
        return findings
    root = roots[0]
    findings.extend(f"{path.name}: {error}" for error in scanner.errors)
    for node in scanner.nodes:
        if node is root or root in node.ancestors():
            if node.duplicates:
                fail(node, f"duplicate attributes: {', '.join(sorted(node.duplicates))}")

    scopes: dict[str, Box] = {}
    nodes: dict[str, Box] = {}
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

    for node in scanner.nodes:
        if root not in node.ancestors() and node is not root:
            continue
        attrs = node.attrs
        if "data-scope-id" in attrs:
            identity = attrs.get("data-scope-id", "")
            kind = attrs.get("data-scope-kind", "")
            if "data-parent" in attrs:
                parent_id = attrs.get("data-parent", "")
                if not identity_ok(parent_id):
                    fail(node, "data-parent must name the enclosing scope")
                    parent_id = parent_id or None
            else:
                parent_id = None
            if attrs.get("data-role") != "bounds":
                fail(node, "scope bounds must declare data-role=\"bounds\"")
            if kind not in SCOPE_KINDS:
                fail(node, "data-scope-kind must be admin or traffic")
            if not register(identity, node):
                continue
            try:
                box = parse_box(node, identity, kind, parent_id)
            except ValueError as error:
                fail(node, str(error))
                continue
            if kind == "admin":
                if box.rx is None or abs(box.rx - ADMIN_RX) > EPS:
                    fail(node, "admin band must use rx=4")
                if not box.dashed:
                    fail(node, "admin band must use a dashed stroke")
                if box.w + EPS < box.h:
                    fail(node, "admin band must be a horizontal rectangle")
            elif kind == "traffic":
                if box.rx is None or abs(box.rx - TRAFFIC_RX) > EPS:
                    fail(node, "traffic box must use rx=8")
                if box.dashed:
                    fail(node, "traffic box must use a solid stroke")
            for value in (box.x, box.y, box.w, box.h):
                if not on_grid(value):
                    fail(node, "scope bounds must sit on the 4px grid")
                    break
            scopes[identity] = box
        elif "data-node-id" in attrs:
            identity = attrs.get("data-node-id", "")
            kind = attrs.get("data-kind", "")
            parent_id = attrs.get("data-parent", "")
            target = attrs.get("data-target")
            target = target if target not in (None, "") else None
            if kind not in NODE_KINDS:
                fail(node, "data-kind must be compute, endpoint, or managed")
            if not identity_ok(parent_id):
                fail(node, "data-parent must name the enclosing scope")
            if not register(identity, node):
                continue
            bounds = [child for child in node.children if child.attrs.get("data-role") == "bounds"]
            if len(bounds) != 1:
                fail(node, "node must expose exactly one data-role=\"bounds\" rect")
                continue
            try:
                box = parse_box(bounds[0], identity, kind, parent_id, target)
            except ValueError as error:
                fail(bounds[0], str(error))
                continue
            box.node = node
            for value in (box.x, box.y, box.w, box.h):
                if not on_grid(value):
                    fail(bounds[0], "node bounds must sit on the 4px grid")
                    break
            if kind == "endpoint":
                if not identity_ok(target or ""):
                    fail(node, "endpoint must declare data-target naming a managed node")
            elif target is not None:
                fail(node, "only an endpoint may declare data-target")
            nodes[identity] = box

    if not any(box.kind == "admin" for box in scopes.values()):
        fail(root, "containment requires at least one admin band")
    if not any(box.kind == "traffic" for box in scopes.values()):
        fail(root, "containment requires at least one traffic box")
    admin_count = sum(1 for box in scopes.values() if box.kind == "admin")
    traffic_count = sum(1 for box in scopes.values() if box.kind == "traffic")
    if admin_count > MAX_ADMIN:
        fail(root, "admin budget is 2 bands")
    if traffic_count > MAX_TRAFFIC:
        fail(root, "traffic budget is 4 scopes")
    if len(nodes) > MAX_NODES:
        fail(root, "node budget is 8")

    known_scopes = set(scopes)
    for box in scopes.values():
        if box.parent_id is None:
            continue
        if not identity_ok(box.parent_id) or box.parent_id not in known_scopes:
            fail(box.node, f'data-parent "{box.parent_id}" does not match any data-scope-id')
            continue
        parent = scopes[box.parent_id]
        if not within_box(box, parent):
            fail(box.node, f'scope "{box.identity}" is not geometrically inside parent "{box.parent_id}"')

    parent_of = {box.identity: box.parent_id for box in scopes.values()}
    reported: set[str] = set()
    for identity in scopes:
        if identity in reported:
            continue
        chain: list[str] = []
        current: str | None = identity
        while current is not None:
            if current in chain:
                cycle = chain[chain.index(current):] + [current]
                reported.update(cycle)
                fail(scopes[identity].node, f'parent cycle: {" -> ".join(cycle)}')
                break
            chain.append(current)
            if current not in known_scopes:
                break
            current = parent_of.get(current)

    traffic = {identity: box for identity, box in scopes.items() if box.kind == "traffic"}
    managed = {identity: box for identity, box in nodes.items() if box.kind == "managed"}

    for box in nodes.values():
        if box.parent_id not in known_scopes:
            fail(box.node, f'data-parent "{box.parent_id}" does not match any data-scope-id')
            continue
        parent = scopes[box.parent_id]
        if not within_box(box, parent):
            fail(box.node, f'node "{box.identity}" is not geometrically inside parent "{box.parent_id}"')
        if box.kind == "managed":
            if parent.kind != "admin":
                fail(box.node, "managed node must parent to an admin band")
            for traffic_id, traffic_box in traffic.items():
                if overlaps(box, traffic_box) or within_box(box, traffic_box):
                    fail(box.node, f'managed node "{box.identity}" must not sit inside traffic scope "{traffic_id}"')
                    break
        elif box.kind in {"compute", "endpoint"}:
            if parent.kind != "traffic":
                fail(box.node, f'{box.kind} node must parent to a traffic box')
            if not within_box(box, parent):
                fail(box.node, f'{box.kind} node "{box.identity}" must sit inside its traffic parent')
        if box.kind == "endpoint":
            if box.target not in managed:
                fail(box.node, f'data-target "{box.target}" must name a managed node')

    siblings: dict[str | None, list[Box]] = {}
    for box in scopes.values():
        if box.kind != "traffic":
            continue
        siblings.setdefault(box.parent_id, []).append(box)
    for parent_id, group in siblings.items():
        if len(group) < 2 or parent_id not in scopes:
            continue
        parent = scopes[parent_id]
        row = parent.w + EPS >= parent.h
        origins = {round(item.y, 6) for item in group} if row else {round(item.x, 6) for item in group}
        if len(origins) > 1:
            fail(group[0].node, "sibling traffic scopes must share one axis")
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                if overlaps(left, right):
                    fail(left.node, f'sibling traffic scopes "{left.identity}" and "{right.identity}" overlap')

    for node in scanner.nodes:
        if root not in node.ancestors() and node is not root:
            continue
        if "data-peering" not in node.attrs:
            continue
        peering = node.attrs.get("data-peering", "")
        source = node.attrs.get("data-from", "")
        target = node.attrs.get("data-to", "")
        if not identity_ok(peering):
            fail(node, "data-peering must be a single XML Name starting with a letter")
        if source not in traffic or target not in traffic:
            fail(node, "peering data-from and data-to must name traffic scopes")
        elif source == target:
            fail(node, "peering must join two distinct traffic scopes")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument("--all", action="store_true", help="check every shipped architecture containment example")
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
        if not looks_like_containment(source):
            continue
        checked += 1
        findings.extend(check_source(path, source))
    if not checked:
        print("error: no architecture containment diagrams found", file=sys.stderr)
        return 1
    for finding in findings:
        print(finding)
    if findings:
        print(f"{len(findings)} architecture containment finding(s) across {checked} file(s).")
        return 1
    print(f"OK architecture containment: {checked} file(s); IDs, parents, geometry, PaaS placement and peerings agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
