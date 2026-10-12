# Preserve optional commented SVG definitions (PR #382)

## Context

The shipped template keeps its optional dot pattern in an SVG comment. Removing
commented definitions from ID collection leaves that pattern unnamespaced if a
consumer uncomments it. Maintainer review requested preserving this behavior
while retaining the original PR's targeted correctness fix.

## Decision

Rebase onto upstream 119ddae (plugin 2.6.81), preserving the export batch and #414 nested-SVG/comment validation. ID collection parses actual attributes. Optional comments use the explicit eight definition element types; live reusable definitions retain main namespacing. Metadata and live accessibility IDs are preserved. Regression methods use PR-specific names to avoid collisions.

## Alternatives

Ignoring commented definitions avoids matching inactive markup but breaks the
shipped template contract. Renaming every matching ID can change unrelated live
elements. The selected scope preserves optional definitions and the original fix.

## Consequences

Optional commented patterns keep a slug-prefixed ID and matching URL reference.
No render, network, release, or merge behavior is added by this correction.

## Validation

The refreshed standalone SVG export suite passes 61 tests, including template-dots, live-title accessibility, and upstream shipped-asset regressions. Full policy and hosted checks are separate gates. Earlier frozen before/after controls remain in local evidence.
