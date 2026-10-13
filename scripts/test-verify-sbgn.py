#!/usr/bin/env python3
"""Adversarial and legal SBGN fixtures (ADR 0005).

Run: python3 scripts/test-verify-sbgn.py
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-sbgn.py"
SPEC = importlib.util.spec_from_file_location("sbgn_verifier", CHECKER)
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def fixture():
    return """<html><body>
<svg data-diagram="sbgn" viewBox="0 0 400 200">
  <rect data-kind="compartment" data-compartment-id="cyt" data-role="bounds"
        x="16" y="16" width="368" height="168" rx="8"/>
  <g data-kind="macromolecule" data-entity-id="a" data-compartment="cyt">
    <rect data-role="bounds" x="32" y="40" width="80" height="40" rx="16"/>
  </g>
  <g data-kind="process" data-process-id="p" data-compartment="cyt">
    <rect data-role="bounds" x="160" y="44" width="32" height="32" rx="2"/>
  </g>
  <g data-kind="macromolecule" data-entity-id="b" data-compartment="cyt">
    <rect data-role="bounds" x="240" y="40" width="80" height="40" rx="16"/>
  </g>
  <path data-kind="consumption" data-from="a" data-to="p" d="M 112,60 H 160"/>
  <path data-kind="production" data-from="p" data-to="b" d="M 192,60 H 240"/>
</svg></body></html>
"""


GOOD = fixture()
SYNTHETIC_PATH = Path("synthetic-sbgn.html")


class ContractTests(unittest.TestCase):
    def clean(self, source):
        self.assertEqual(checker.check_source(SYNTHETIC_PATH, source), [])

    def rejects(self, source, reason):
        self.assertNotEqual(source, GOOD, "fixture mutation did not apply")
        findings = checker.check_source(SYNTHETIC_PATH, source)
        self.assertTrue(findings, "invalid diagram accepted")
        self.assertIn(reason, "\n".join(findings))

    def test_synthetic_is_clean(self):
        self.clean(GOOD)

    def test_files_without_diagram_are_skipped(self):
        source = GOOD.replace('data-diagram="sbgn"', "")
        self.assertEqual(checker.check_source(SYNTHETIC_PATH, source), [])
        self.assertFalse(checker.looks_like_sbgn(source))

    def test_comments_and_unquoted(self):
        source = GOOD.replace("</svg>", "<!-- <g data-entity-id=\"bogus\"/> --></svg>")
        source = source.replace('data-kind="compartment"', "DATA-KIND=compartment")
        self.clean(source)

    def test_duplicate_id(self):
        self.rejects(GOOD.replace('data-entity-id="a"', 'data-entity-id="b"', 1), "duplicate ID")

    def test_species_process_share_namespace(self):
        self.rejects(GOOD.replace('data-process-id="p"', 'data-process-id="a"', 1), "duplicate ID")

    def test_consumption_must_be_species_to_process(self):
        self.rejects(GOOD.replace('data-from="a" data-to="p"', 'data-from="p" data-to="a"', 1),
                     "consumption must run species → process")

    def test_production_must_be_process_to_species(self):
        self.rejects(GOOD.replace('data-from="p" data-to="b"', 'data-from="a" data-to="b"', 1),
                     "production must run process → species")

    def test_modulation_and_reversible(self):
        source = GOOD.replace(
            "</svg>",
            '<path data-kind="modulation" data-from="a" data-to="p" d="M 112,80 H 160"/>'
            '<path data-kind="reversible" data-from="b" data-to="p" d="M 240,80 H 192"/></svg>',
        )
        self.clean(source)
        self.rejects(GOOD.replace("</svg>",
                                  '<path data-kind="modulation" data-from="p" data-to="a" d="M 192,80 H 112"/></svg>'),
                     "modulation must run species → process")
        self.rejects(GOOD.replace("</svg>",
                                  '<path data-kind="reversible" data-from="a" data-to="b" d="M 112,80 H 240"/></svg>'),
                     "reversible must join a species and a process")

    def test_misspelled_arc_kind_is_rejected(self):
        # A typo used to skip every endpoint check, so a species-to-species
        # arc passed as long as its kind was misspelled.
        self.rejects(GOOD.replace('data-kind="consumption" data-from="a" data-to="p"',
                                  'data-kind="consumtion" data-from="a" data-to="b"', 1),
                     'arc data-kind "consumtion" must be one of')

    def test_missing_arc_kind_is_rejected(self):
        self.rejects(GOOD.replace('data-kind="consumption" data-from="a" data-to="p"',
                                  'data-from="a" data-to="b"', 1),
                     "arc data-kind is missing")
        self.rejects(GOOD.replace("</svg>", '<path data-to="b" d="M 112,80 H 240"/></svg>'),
                     "arc data-kind is missing")

    def test_unknown_glyph_kind_is_rejected(self):
        # A misspelled glyph kind would drop the glyph from the budget and
        # containment checks without a finding.
        self.rejects(GOOD.replace('data-kind="macromolecule" data-entity-id="b"',
                                  'data-kind="macromolecul" data-entity-id="b"', 1),
                     'unknown data-kind "macromolecul"')

    def test_source_sink_is_species(self):
        source = GOOD.replace(
            "</svg>",
            '<g data-kind="source-sink" data-entity-id="src" data-compartment="cyt">'
            '<rect data-role="bounds" x="32" y="120" width="24" height="24"/>'
            "</g>"
            '<path data-kind="consumption" data-from="src" data-to="p" d="M 56,132 H 160"/></svg>',
        )
        self.clean(source)

    def test_outside_compartment(self):
        self.rejects(GOOD.replace('x="32" y="40" width="80" height="40"',
                                  'x="0" y="40" width="80" height="40"', 1),
                     "not geometrically inside compartment")

    def test_missing_compartment_ref(self):
        self.rejects(GOOD.replace('data-compartment="cyt"', 'data-compartment="missing"', 1),
                     "data-compartment must name a compartment")

    def test_off_grid(self):
        self.rejects(GOOD.replace('x="32" y="40"', 'x="33" y="40"'), "4px grid")

    def test_duplicate_attributes(self):
        self.rejects(GOOD.replace('data-entity-id="a"', 'data-entity-id="a" DATA-ENTITY-ID="ignored"', 1),
                     "duplicate attributes")

    def test_budget(self):
        extra = GOOD.replace("</svg>", "".join(
            f'<g data-kind="macromolecule" data-entity-id="m{i}" data-compartment="cyt">'
            f'<rect data-role="bounds" x="32" y="40" width="80" height="40"/></g>'
            for i in range(6)
        ) + "</svg>")
        self.rejects(extra, "macromolecule budget")

    def test_all_shipped_variants(self):
        for suffix in ("", "-dark", "-full"):
            path = ROOT / f"skills/diagram-design/assets/example-sbgn{suffix}.html"
            with self.subTest(variant=suffix):
                self.assertTrue(path.is_file(), f"missing shipped variant: {path.name}")
                source = path.read_text(encoding="utf-8")
                self.assertEqual(checker.check_source(path, source), [])
                self.assertIn('data-diagram="sbgn"', source)
                self.assertIn('data-kind="macromolecule"', source)
                self.assertIn('data-kind="process"', source)
                self.assertIn('data-kind="compartment"', source)

    def test_cli_discovery_and_failures(self):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        for args in ([], ["--all"]):
            result = subprocess.run([sys.executable, str(CHECKER), *args], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("3 file(s)", result.stdout)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagram.html"
            path.write_text(GOOD, encoding="utf-8")
            result = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            path.write_text(GOOD.replace('data-from="a"', 'data-from="p"', 1), encoding="utf-8")
            result = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 1)
            path.unlink()
            result = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
