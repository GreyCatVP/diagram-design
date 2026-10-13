#!/usr/bin/env python3
"""Structural and adversarial verification for PlantUML import.

The driver invokes the shipped extractor as a subprocess, imports its public
module surface for resource-limit checks, and verifies the documentation and
command wiring. Exit 0 only when every gate passes.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills/diagram-design/SKILL.md"
EXTRACT = ROOT / "skills/diagram-design/scripts/plantuml_extract.py"
IMPORT_REF = ROOT / "skills/diagram-design/references/import-plantuml.md"
COMMAND = ROOT / "commands/import-plantuml.md"
PROMPT = ROOT / "prompts/import-plantuml.md"
SEQUENCE = ROOT / "scripts/fixtures/sample-sequence.puml"
CLASS_FIXTURE = ROOT / "scripts/fixtures/sample-class.puml"
ADVERSARIAL = ROOT / "scripts/fixtures/sample-adversarial.puml"
MULTI = ROOT / "scripts/fixtures/sample-multi.puml"
EXAMPLE = ROOT / "skills/diagram-design/assets/example-import-plantuml.html"
OUTPUT_SPEC = ROOT / "skills/diagram-design/references/output-spec.md"
SUPPORTED_KINDS = "sequence, class"


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"OK: {message}")


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def invoke(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(EXTRACT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_extract(args: list[str]) -> str:
    process = invoke(args)
    if process.returncode != 0:
        fail(
            f"extractor exited {process.returncode} for {args}: "
            f"{process.stderr.strip()}"
        )
    return process.stdout


def expect_error(args: list[str], message: str) -> None:
    process = invoke(args)
    if process.returncode != 2 or message not in process.stderr:
        fail(
            f"expected exit 2 containing {message!r} for {args}; got "
            f"{process.returncode}: {process.stderr.strip()!r}"
        )


def load_extractor_module():
    spec = importlib.util.spec_from_file_location(
        "diagram_design_plantuml_extract", EXTRACT
    )
    if spec is None or spec.loader is None:
        fail("could not load PlantUML extractor module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def spec_size_presets() -> list[str]:
    presets: list[str] = []
    in_table = False
    for line in OUTPUT_SPEC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## 2. Size"):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        if in_table:
            match = re.match(r"\| `([a-z0-9-]+)`", line)
            if match:
                presets.append(match.group(1))
    return presets


def check_files() -> None:
    for path in (
        SKILL,
        EXTRACT,
        IMPORT_REF,
        COMMAND,
        PROMPT,
        SEQUENCE,
        CLASS_FIXTURE,
        ADVERSARIAL,
        MULTI,
        EXAMPLE,
    ):
        if not path.is_file():
            fail(f"missing {path.relative_to(ROOT)}")
    ok("all PlantUML import artifacts present")


def check_sequence() -> None:
    payload = json.loads(run_extract([str(SEQUENCE), "--json"]))
    diagram = payload["diagrams"][0]
    nodes = {node["id"]: node for node in diagram["nodes"]}
    edges = diagram["edges"]
    fragments = diagram["fragments"]

    if diagram["kind"] != "sequence":
        fail(f"sequence fixture kind was {diagram['kind']!r}")
    if len(nodes) < 3:
        fail(f"sequence fixture listed {len(nodes)} participants, expected 3+")
    for node_id, label, shape in (
        ("Client", "Client", "actor"),
        ("api", "Resource API", "lifeline"),
        ("auth", "Auth Service", "lifeline"),
    ):
        if node_id not in nodes:
            fail(f"sequence fixture missing participant {node_id}")
        if nodes[node_id]["label"] != label or nodes[node_id]["shape"] != shape:
            fail(f"sequence participant {node_id} lost display name or shape")
    labels = [edge["label"] for edge in edges]
    expected_order = [
        "GET /orders",
        "200 body",
        "401",
        "POST /token",
        "200 access",
        "GET /orders retry",
        "200 body",
        "200 body",
    ]
    if labels != expected_order:
        fail(f"sequence message order drifted: {labels}")
    alts = [item for item in fragments if item["kind"] == "alt"]
    if len(alts) != 1 or alts[0]["label"] != "token expired":
        fail(f"sequence alt fragment missing: {fragments}")
    regions = [
        (region["label"], region["first_message"], region["last_message"])
        for region in alts[0]["regions"]
    ]
    if regions != [("token expired", 3, 7), ("token valid", 8, 8)]:
        fail(f"sequence alt branches lost their message spans: {regions}")
    timeline = [
        (item["participant"], item["action"], item["after_message"])
        for item in diagram["activations"]
    ]
    if timeline[:2] != [("api", "activate", 1), ("api", "deactivate", 2)]:
        fail(f"sequence activations lost their message positions: {timeline}")
    if diagram["discarded"]["skin"] != 4:
        fail(f"sequence skinparam discard count wrong: {diagram['discarded']}")
    if not diagram["activations"]:
        fail("sequence activations were dropped")
    if "fragments" not in payload["diagrams"][0]:
        fail("--json omitted fragments")

    digest = run_extract([str(SEQUENCE), "--max-rows", "3"])
    for needle in (
        "source layout: none (PlantUML is layout-free)",
        "type candidates: sequence",
        "budget:",
        "- discarded: 4 skinparam",
        "alt(token expired) msgs 3-7; else(token valid) msg 8",
        "api:activate@1",
        "| # | source | target | label | style |",
        "### Nodes",
        "### Edges",
        "+",
    ):
        if needle not in digest:
            fail(f"sequence digest missing {needle!r}")
    ok("sequence parses: participants, order, alt, activations, skinparam ledger")


def check_class() -> None:
    payload = json.loads(run_extract([str(CLASS_FIXTURE), "--json"]))
    diagram = payload["diagrams"][0]
    nodes = {node["id"]: node for node in diagram["nodes"]}
    edges = diagram["edges"]

    if diagram["kind"] != "class":
        fail(f"class fixture kind was {diagram['kind']!r}")
    if nodes["Account"]["shape"] != "abstract":
        fail("abstract class was not classified")
    if nodes["Store"]["shape"] != "interface":
        fail("interface was not classified")
    if "+ balance(): Money" not in nodes["Account"]["fields"]:
        fail("class members were not retained")
    kinds = {edge["arrowhead"] for edge in edges}
    if "inheritance" not in kinds or "composition" not in kinds:
        fail(f"class relationship kinds missing: {kinds}")
    composition = next(edge for edge in edges if edge["arrowhead"] == "composition")
    if "1" not in composition["cardinality"] or "many" not in composition["cardinality"]:
        fail(f"composition cardinality missing: {composition}")
    if diagram["analysis"]["type_candidates"] != ["UML class"]:
        fail(f"class type candidates drifted: {diagram['analysis']['type_candidates']}")

    digest = run_extract([str(CLASS_FIXTURE)])
    if "inheritance" not in digest or "composition" not in digest:
        fail("class digest omitted relationship kinds")
    ok("class parses: members, inheritance, composition, cardinality")


def write_puml(tmp: Path, name: str, body: str) -> Path:
    path = tmp / name
    path.write_text(f"@startuml\n{body}\n@enduml\n", encoding="utf-8")
    return path


def extract_json(path: Path) -> dict:
    return json.loads(run_extract([str(path), "--json"]))["diagrams"][0]


def check_review_regressions(tmp: Path) -> None:
    """Pin the import-fidelity fixes from the PR #358 review threads."""
    # Declaration tails are parsed, never used as ids.
    diagram = extract_json(
        write_puml(
            tmp,
            "tails.puml",
            "participant A #red\nparticipant B #red\nparticipant C <<svc>> order 3\n"
            "A -> B : hi\nB -> C : go",
        )
    )
    ids = [node["id"] for node in diagram["nodes"]]
    if ids != ["A", "B", "C"]:
        fail(f"participant tails became ids: {ids}")
    if diagram["nodes"][2]["stereotype"] != "svc":
        fail("participant stereotype was not kept")
    diagram = extract_json(write_puml(tmp, "inline.puml", "class A { +id: int }\nclass B\nA --> B"))
    nodes = {node["id"]: node for node in diagram["nodes"]}
    if set(nodes) != {"A", "B"} or nodes["A"]["fields"] != ["+id: int"]:
        fail(f"inline class body became an id or lost its member: {diagram['nodes']}")
    expect_error([str(write_puml(tmp, "tail-junk.puml", "participant A extra\nA -> A : x"))], "malformed statement at line 2")
    expect_error([str(write_puml(tmp, "class-junk.puml", "class A extends B\nA --> C"))], "malformed statement at line 2")

    # Exact ids are case-sensitive.
    diagram = extract_json(write_puml(tmp, "case.puml", "participant a\nparticipant A\na -> A : ping"))
    edge = diagram["edges"][0]
    if (edge["source"], edge["target"]) != ("a", "A"):
        fail(f"letter case redirected a message: {edge}")

    # Same-named classes in different packages stay separate.
    diagram = extract_json(
        write_puml(
            tmp,
            "packages.puml",
            "package billing {\n  class User {\n    +plan\n  }\n}\n"
            "package auth {\n  class User {\n    +password\n  }\n  User --> Session\n}\n"
            "billing.User --> auth.User",
        )
    )
    nodes = {node["id"]: node for node in diagram["nodes"]}
    if nodes.get("billing.User", {}).get("fields") != ["+plan"] or nodes.get("auth.User", {}).get("fields") != ["+password"]:
        fail(f"classes merged across packages: {list(nodes)}")
    pairs = [(edge["source"], edge["target"]) for edge in diagram["edges"]]
    if pairs != [("auth.User", "Session"), ("billing.User", "auth.User")]:
        fail(f"package-qualified relationships resolved wrongly: {pairs}")
    expect_error(
        [str(write_puml(tmp, "ambiguous.puml", "package a {\n class User\n}\npackage b {\n class User\n}\nUser --> X"))],
        "ambiguous class name `User`",
    )

    # Styling commands match whole words only.
    diagram = extract_json(write_puml(tmp, "show.puml", "ShowService -> Client : result\nScale -> Client : size"))
    if [edge["label"] for edge in diagram["edges"]] != ["result", "size"]:
        fail(f"styling prefix dropped a message: {diagram['edges']}")
    diagram = extract_json(write_puml(tmp, "show-member.puml", "class View {\n  show(): void\n  hide(): void\n}"))
    if diagram["nodes"][0]["fields"] != ["show(): void", "hide(): void"]:
        fail(f"styling prefix dropped class members: {diagram['nodes'][0]['fields']}")

    # Multi-line styling blocks are consumed whole.
    diagram = extract_json(
        write_puml(
            tmp,
            "skin-block.puml",
            "skinparam sequence {\n  ArrowColor red\n  LifeLineBorderColor blue\n}\n"
            "legend right\n  shorthand\nendlegend\nAlice -> Bob : hi",
        )
    )
    if [edge["label"] for edge in diagram["edges"]] != ["hi"] or diagram["discarded"]["skin"] != 2:
        fail(f"multiline styling block was not consumed: {diagram['discarded']}")
    expect_error([str(write_puml(tmp, "skin-open.puml", "Alice -> Bob : hi\nskinparam sequence {\n  ArrowColor red"))], "unterminated styling block at line 3")

    # Open class or package bodies fail instead of swallowing relationships.
    expect_error([str(write_puml(tmp, "brace.puml", "class A {\n  +id\nA --> B"))], "unterminated class body at line 2")
    expect_error([str(write_puml(tmp, "package-open.puml", "package p {\n  class A\nA --> B"))], "unterminated package at line 2")

    # Region splitting honors block comments.
    commented = tmp / "comment-end.puml"
    commented.write_text(
        "@startuml\nAlice -> Bob : one\n/'\n@enduml\n'/\nBob -> Alice : two\n@enduml\n",
        encoding="utf-8",
    )
    diagram = extract_json(commented)
    if [edge["label"] for edge in diagram["edges"]] != ["one", "two"]:
        fail(f"@enduml inside a block comment cut the diagram short: {diagram['edges']}")
    open_comment = tmp / "comment-open.puml"
    open_comment.write_text("@startuml\nAlice -> Bob : one\n/'\n@enduml\n", encoding="utf-8")
    expect_error([str(open_comment)], "unterminated block comment at line 3")

    # Stereotypes reach the default digest.
    digest = run_extract([str(write_puml(tmp, "stereo.puml", "class Account <<entity>>\nclass Ledger\nLedger --> Account"))])
    if "| Account | Account | class | entity |" not in digest:
        fail(f"class stereotype missing from the default digest: {digest!r}")
    ok("review regressions: timeline positions, declaration tails, case, packages, styling, braces, comments, stereotypes")


def check_kind_detection_skips_bodies(tmp: Path) -> None:
    """Note, legend, and class bodies are text, not statements, when picking the kind."""
    diagram = extract_json(
        write_puml(
            tmp,
            "note-body-kind.puml",
            "participant A\nparticipant B\nnote over A\n  class Foo\n  interface Bar\nend note\n"
            "legend\n  class Legend\nendlegend\nA -> B : hi",
        )
    )
    if diagram["kind"] != "sequence" or [edge["label"] for edge in diagram["edges"]] != ["hi"]:
        fail(f"note or legend body changed the diagram kind: {diagram['kind']}")
    if "class Foo\ninterface Bar" not in diagram["notes"]:
        fail(f"multiline note body was not kept as note text: {diagram['notes']}")
    diagram = extract_json(
        write_puml(
            tmp,
            "member-kind.puml",
            "class Casting {\n  participant: Person\n  actor: Role\n}\nclass Person\nCasting --> Person",
        )
    )
    if diagram["kind"] != "class" or diagram["nodes"][0]["fields"] != ["participant: Person", "actor: Role"]:
        fail(f"class members that look like declarations changed the kind: {diagram['kind']}")
    ok("kind detection ignores note, legend, and class body text")


def check_digest_edges_use_ids(tmp: Path) -> None:
    """Same-named classes stay distinguishable in the default digest."""
    source = write_puml(
        tmp,
        "edge-ids.puml",
        "package billing {\n  class User\n}\npackage auth {\n  class User\n}\n"
        "billing.User --> auth.User : syncs",
    )
    digest = run_extract([str(source)])
    row = r"| 1 | billing\.User \(User\) | auth\.User \(User\) | syncs |"
    if row not in digest:
        fail(f"edge table lost the class ids of its endpoints: {digest!r}")
    if r"- entry points: billing\.User \(User\)" not in digest:
        fail(f"entry points lost the class id: {digest!r}")
    sequence = run_extract([str(SEQUENCE)])
    if r"| 1 | Client | api \(Resource API\) | GET /orders |" not in sequence:
        fail(f"sequence edge table lost participant ids: {sequence!r}")
    ok("digest edges and summaries name endpoints by id, with the label alongside")


def check_unselected_comment_isolated(tmp: Path) -> None:
    """An unclosed block comment fails only the block that contains it."""
    source = tmp / "unselected-comment.puml"
    source.write_text(
        "@startuml\nAlice -> Bob : one\n@enduml\n\n"
        "@startuml\nCarol -> Dan : two\n/'\nnever closed\n@enduml\n",
        encoding="utf-8",
    )
    for args in ([str(source)], [str(source), "--diagram", "0"]):
        digest = run_extract(args)
        if "[1] unparsed: unterminated block comment at line 7" not in digest:
            fail(f"unselected block with an open comment was not listed as unparsed: {digest!r}")
        if "## Diagram 0" not in digest:
            fail("selected block was not emitted past an open comment elsewhere")
    expect_error([str(source), "--diagram", "1"], "unterminated block comment at line 7")
    expect_error([str(source), "--diagram", "all"], "unterminated block comment at line 7")
    fenced = tmp / "unselected-comment.md"
    fenced.write_text(
        "```plantuml\n@startuml\nAlice -> Bob : one\n@enduml\n```\n\n"
        "```plantuml\n@startuml\nCarol -> Dan : two\n/'\n@enduml\n```\n",
        encoding="utf-8",
    )
    if "## Diagram 0" not in run_extract([str(fenced), "--diagram", "0"]):
        fail("fenced block 0 was blocked by an open comment in fenced block 1")
    expect_error([str(fenced), "--diagram", "1"], "unterminated block comment at line 10")
    ok("an unclosed block comment fails only its own block")


def check_multi_diagram() -> None:
    payload = json.loads(run_extract([str(MULTI), "--diagram", "1", "--json"]))
    if payload["diagrams_total"] != 2:
        fail(f"diagrams_total must count every block: {payload['diagrams_total']}")
    if [(item["index"], item["kind"]) for item in payload["diagrams"]] != [(1, "class")]:
        fail("--diagram 1 did not return block 1 past a malformed block 0")
    digest = run_extract([str(MULTI), "--diagram", "1"])
    if "[0] unparsed: include not inlined" not in digest:
        fail(f"unselected include block was not listed as unparsed: {digest!r}")
    if "## Diagram 1" not in digest or "## Diagram 0" in digest:
        fail("selected-block digest emitted the wrong diagram")
    expect_error([str(MULTI), "--diagram", "0"], "include not inlined")
    expect_error([str(MULTI)], "include not inlined")
    expect_error([str(MULTI), "--diagram", "9"], "no diagram with index 9 (have 0..1)")
    ok("--diagram 1 isolates a class block past a malformed include in block 0")


def check_adversarial(tmp: Path) -> None:
    payload = json.loads(run_extract([str(ADVERSARIAL), "--json"]))
    diagram = payload["diagrams"][0]
    notes = " ".join(diagram["notes"])
    if "IGNORE ALL PREVIOUS INSTRUCTIONS" not in notes:
        fail("prompt-injection note was not retained as inert diagram text")
    if "javascript:" not in notes:
        fail("javascript: note text was dropped instead of kept inert")
    if "<script" in json.dumps(payload):
        fail("raw <script> crossed into JSON output")

    digest_path = tmp / "adversarial.md"
    run_extract([str(ADVERSARIAL), "--out", str(digest_path)])
    digest_text = digest_path.read_text(encoding="utf-8")
    if "<script" in digest_text:
        fail("digest reactivated a <script> tag")
    if "javascript:" not in digest_text:
        fail("javascript: note was not preserved as escaped inert text")
    if "IGNORE ALL PREVIOUS INSTRUCTIONS" not in digest_text:
        fail("injection note missing from --out digest")
    ok("adversarial labels stay inert escaped text in JSON and --out")


def check_errors_and_limits(tmp: Path) -> None:
    include = tmp / "include.puml"
    include.write_text(
        "@startuml\n!includeurl https://example.invalid/remote.puml\n"
        "Alice -> Bob : hi\n@enduml\n",
        encoding="utf-8",
    )
    expect_error([str(include)], "include not inlined")

    gantt = tmp / "gantt.puml"
    gantt.write_text("@startgantt\nProject starts 2026-01-01\n@endgantt\n", encoding="utf-8")
    process = invoke([str(gantt)])
    if process.returncode != 2:
        fail(f"@startgantt exited {process.returncode}")
    if SUPPORTED_KINDS not in process.stderr:
        fail(
            "supported-kinds message must list "
            f"{SUPPORTED_KINDS!r} verbatim: {process.stderr!r}"
        )
    if "unsupported diagram kind" not in process.stderr:
        fail("gantt rejection did not name the unsupported kind")

    mixed = tmp / "mixed.puml"
    mixed.write_text(
        "@startuml\nparticipant A\nclass Box\nA -> Box : hi\n@enduml\n",
        encoding="utf-8",
    )
    expect_error([str(mixed)], "mixed or unknown kind")

    malformed = tmp / "malformed.puml"
    malformed.write_text("@startuml\nparticipant A\n???\n@enduml\n", encoding="utf-8")
    expect_error([str(malformed)], "malformed statement at line")

    extractor = load_extractor_module()
    oversize = tmp / "oversize.puml"
    oversize.write_bytes(b"x" * (extractor.MAX_SOURCE_BYTES + 2))
    expect_error([str(oversize)], "4 MiB")

    long_line = tmp / "long-line.puml"
    cap = extractor.MAX_STATEMENT_CHARS
    long_line.write_text(
        "@startuml\nparticipant A\nA -> B : " + ("x" * (cap + 8)) + "\n@enduml\n",
        encoding="utf-8",
    )
    expect_error(
        [str(long_line)],
        f"statement at line 3 exceeds the {cap}-character limit",
    )

    empty = tmp / "empty.puml"
    empty.write_text("@startuml\n@enduml\n", encoding="utf-8")
    expect_error([str(empty)], "mixed or unknown kind")

    state = tmp / "state.puml"
    state.write_text("@startuml\nstate Active\n[*] --> Active\n@enduml\n", encoding="utf-8")
    expect_error([str(state)], "unsupported diagram kind")
    expect_error([str(state)], SUPPORTED_KINDS)

    fenced = tmp / "fenced.md"
    fenced.write_text(
        "# Notes\n\n```plantuml\n@startuml\nAlice -> Bob : ping\n@enduml\n```\n",
        encoding="utf-8",
    )
    payload = json.loads(run_extract([str(fenced), "--json"]))
    if payload["diagrams"][0]["kind"] != "sequence":
        fail("fenced plantuml block was not parsed as sequence")
    if payload["diagrams"][0]["edges"][0]["label"] != "ping":
        fail("fenced plantuml block dropped the message label")

    too_many_nodes = tmp / "nodes.puml"
    too_many_nodes.write_text(
        "@startuml\n"
        + "\n".join(f"participant N{index}" for index in range(extractor.MAX_NODES + 1))
        + "\nN0 -> N1 : ping\n@enduml\n",
        encoding="utf-8",
    )
    expect_error(
        [str(too_many_nodes)],
        f"node limit exceeded (max {extractor.MAX_NODES})",
    )

    too_many_edges = tmp / "edges.puml"
    too_many_edges.write_text(
        "@startuml\nparticipant A\nparticipant B\n"
        + "\n".join("A -> B : ping" for _ in range(extractor.MAX_EDGES + 1))
        + "\n@enduml\n",
        encoding="utf-8",
    )
    expect_error(
        [str(too_many_edges)],
        f"edge limit exceeded (max {extractor.MAX_EDGES})",
    )

    expect_error([str(SEQUENCE), "--diagram", "first"], "--diagram must be an index or 'all'")
    expect_error([str(SEQUENCE), "--max-rows", "0"], "--max-rows must be at least 1")
    ok("all documented exit-2 paths and resource caps fire specifically")


def check_legacy_stdout_encoding(tmp: Path) -> None:
    source = tmp / "unicode-stdout.puml"
    source.write_text(
        '@startuml\nparticipant "登录" as a\nparticipant "résumé" as b\na -> b : 続行 ⇒\n@enduml\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"
    env["PYTHONUTF8"] = "0"
    process = subprocess.run(
        [sys.executable, str(EXTRACT), str(source)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if process.returncode != 0:
        fail(
            "PlantUML extractor failed with legacy stdout encoding: "
            + process.stderr.decode("utf-8", errors="replace").strip()
        )
    try:
        output = process.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        fail(f"PlantUML extractor did not emit UTF-8 stdout: {error}")
    for needle in ("登录", "続行 ⇒", "résumé"):
        if needle not in output:
            fail(f"UTF-8 PlantUML digest lost {needle!r}: {output!r}")
    if "�" in output:
        fail("UTF-8 PlantUML digest contains a replacement character")
    destination = tmp / "unicode-stdout.md"
    file_process = subprocess.run(
        [sys.executable, str(EXTRACT), str(source), "--out", str(destination)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if file_process.returncode != 0:
        fail("PlantUML --out failed under a legacy Windows encoding")
    file_output = destination.read_text(encoding="utf-8")
    if normalize_newlines(file_output) != normalize_newlines(output):
        fail("PlantUML --out no longer matches its UTF-8 stdout digest")

    class CallerOwnedStdout(io.StringIO):
        def __init__(self) -> None:
            super().__init__()
            self.reconfigured = False

        def reconfigure(self, **_kwargs: object) -> None:
            self.reconfigured = True

    caller_stdout = CallerOwnedStdout()
    extractor = load_extractor_module()
    with contextlib.redirect_stdout(caller_stdout):
        result = extractor.main([str(source)])
    if result != 0 or caller_stdout.reconfigured:
        fail("imported PlantUML main() reconfigured its caller-owned stdout")
    if "登录" not in caller_stdout.getvalue():
        fail("imported PlantUML main() did not write to its caller-owned stdout")
    ok("PlantUML stdout stays lossless UTF-8 under a legacy Windows encoding")


def check_docs_and_wiring() -> None:
    import_text = IMPORT_REF.read_text(encoding="utf-8")
    expected_slash_command = f"/diagram-design:{COMMAND.stem}"
    documented_slash_commands = set(
        re.findall(r"`(/diagram-design:[a-z0-9-]+)`", import_text)
    )
    if documented_slash_commands != {expected_slash_command}:
        rendered = ", ".join(sorted(documented_slash_commands)) or "none"
        fail(
            "import-plantuml.md slash command does not match "
            f"{COMMAND.name}: expected {expected_slash_command}, found {rendered}"
        )
    for needle in (
        "plantuml_extract.py",
        "output-spec.md",
        "## Step 1 — Extract the IR",
        "## Step 2 — Set the four dials",
        "## Step 3 — Pick the target type",
        "## Step 4 — Build the semantic model",
        "## Step 5 — Redraw",
        "## Step 6 — Deliver",
        "## Worked example",
        "Multi-block files",
        "## Edge cases",
        "## Anti-patterns",
        "fidelity ledger",
        "untrusted data",
        "never renders, fetches, or executes",
        "--diagram all",
        "example-import-plantuml.html",
        "include not inlined",
        SUPPORTED_KINDS,
    ):
        if needle not in import_text:
            fail(f"import-plantuml.md missing {needle!r}")

    skill_text = SKILL.read_text(encoding="utf-8")
    for needle in (
        "references/import-plantuml.md",
        "plantuml_extract.py",
        ".puml",
        "PlantUML",
    ):
        if needle not in skill_text:
            fail(f"SKILL.md missing PlantUML router text {needle!r}")
    if "PlantUML" not in skill_text.split("---")[1]:
        fail("SKILL.md frontmatter description does not mention PlantUML")
    if "## 11." not in skill_text or "import-plantuml.md" not in skill_text:
        fail("SKILL.md §11 does not name the PlantUML route")

    command_text = COMMAND.read_text(encoding="utf-8")
    reference_flags = (
        "--format",
        "--size",
        "--detail",
        "--audience",
        "--type",
        "--diagram",
        "--variant",
        "--output",
    )
    for flag in reference_flags:
        if flag not in command_text or flag not in import_text:
            fail(f"command/reference flag drift: {flag}")
    if "references/import-plantuml.md" not in command_text:
        fail("command unlinked from references/import-plantuml.md")
    if "references/import-plantuml.md" not in PROMPT.read_text(encoding="utf-8"):
        fail("Pi prompt unlinked from references/import-plantuml.md")
    if "advertised by Pi" not in PROMPT.read_text(encoding="utf-8"):
        fail("Pi prompt does not discover the skill via advertised SKILL.md")

    size_marker = "- `--size` — any preset in `output-spec.md` §2:"
    size_line = next(
        (line for line in command_text.splitlines() if line.startswith(size_marker)),
        "",
    )
    listed = re.findall(r"`([a-z0-9-]+)`", size_line[len(size_marker) :])
    expected = spec_size_presets()
    if listed != expected:
        fail(
            "command --size line must list every output-spec.md §2 preset in order: "
            f"expected {expected}, found {listed}"
        )

    example = EXAMPLE.read_text(encoding="utf-8")
    if 'viewBox="0 0 960 600"' not in example:
        fail("worked example does not use the doc-inline viewBox")
    if example.count("#eb6c36") > 4:
        fail("worked example uses the accent on more than the focal node + legend")
    if '<div class="diagram-container">' not in example or "overflow-x:auto" not in example:
        fail("worked example must contain its wide SVG in a local horizontal scroller")
    lint = subprocess.run(
        [sys.executable, str(ROOT / "scripts/lint-skin.py"), str(EXAMPLE)],
        capture_output=True,
        text=True,
    )
    if lint.returncode != 0:
        fail(f"worked example fails lint-skin: {lint.stdout.strip() or lint.stderr.strip()}")
    ok("reference, SKILL.md, command, prompt, and example stay in sync")


def check_mobile_example() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        ok("worked example has the static mobile-containment contract (browser check runs in lint-render)")
        return
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.route("http*", lambda route: route.abort())
        page = context.new_page()
        page.goto(EXAMPLE.resolve().as_uri(), wait_until="load")
        facts = page.evaluate(
            """
            () => {
              const documentElement = document.documentElement;
              const svg = document.querySelector('svg');
              const scroller = svg && svg.parentElement;
              const overflow = scroller && getComputedStyle(scroller).overflowX;
              return {
                pageOverflow: documentElement.scrollWidth - documentElement.clientWidth,
                svgWidth: svg ? svg.getBoundingClientRect().width : 0,
                localScroller: Boolean(scroller &&
                  (overflow === 'auto' || overflow === 'scroll') &&
                  scroller.scrollWidth > scroller.clientWidth + 1),
              };
            }
            """
        )
        browser.close()
    if facts["pageOverflow"] > 1:
        fail(f"worked example overflows the 390px page by {facts['pageOverflow']:.1f}px")
    if facts["svgWidth"] < 900:
        fail("worked example shrinks its labeled SVG below the 900px legibility floor")
    if not facts["localScroller"]:
        fail("worked example lacks a functioning local horizontal scroller at 390px")
    ok("worked example is contained and locally scrollable at 390px")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="diagram-design-plantuml-") as directory:
        tmp = Path(directory)
        check_files()
        check_sequence()
        check_class()
        check_multi_diagram()
        check_review_regressions(tmp)
        check_kind_detection_skips_bodies(tmp)
        check_digest_edges_use_ids(tmp)
        check_unselected_comment_isolated(tmp)
        check_adversarial(tmp)
        check_errors_and_limits(tmp)
        check_legacy_stdout_encoding(tmp)
        check_docs_and_wiring()
        check_mobile_example()
    print("\nAll PlantUML import gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
