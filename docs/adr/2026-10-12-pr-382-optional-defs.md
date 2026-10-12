# Preserve optional commented SVG definitions (PR #382)

## Context

The shipped template keeps its optional dot pattern in an SVG comment. Removing
commented definitions from ID collection leaves that pattern unnamespaced if a
consumer uncomments it. Maintainer review requested preserving this behavior
while retaining the original PR's targeted correctness fix.

## Decision

Collect actual ID attributes from referenceable defs tags inside comments as well as live markup, retaining metadata protection and reference-like text preservation.

Merge current upstream main before applying the correction. Leave package versions
at upstream values and keep the change confined to the exporter, its tests, and
its export reference.

## Alternatives

Ignoring commented definitions avoids matching inactive markup but breaks the
shipped template contract. Renaming every matching ID can change unrelated live
elements. The selected scope preserves optional definitions and the original fix.

## Consequences

Optional commented patterns keep a slug-prefixed ID and matching URL reference.
No render, network, release, or merge behavior is added by this correction.

## Validation

The new shipped-template regression fails on the frozen pre-correction branch
and passes after the correction. The standalone SVG export suite passes all
32 tests, including its shipped asset checks. Full repository validation and
hosted CI are separate gates; this scoped result does not claim either passed.
