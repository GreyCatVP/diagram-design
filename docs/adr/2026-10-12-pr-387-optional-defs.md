# Preserve optional commented SVG definitions (PR #387)

## Context

The shipped template keeps its optional dot pattern in an SVG comment. Removing
commented definitions from ID collection leaves that pattern unnamespaced if a
consumer uncomments it. Maintainer review requested preserving this behavior
while retaining the original PR's targeted correctness fix.

## Decision

Rebase onto upstream 119ddae (plugin 2.6.81), preserving the export batch and #414 nested-SVG/comment validation. Optional comments use the explicit eight definition element types. Live reusable shapes under defs retain main namespacing; shapes outside defs are not renamed by a commented-ID collision. Regression methods use PR-specific names to avoid collisions.

## Alternatives

Ignoring commented definitions avoids matching inactive markup but breaks the
shipped template contract. Renaming every matching ID can change unrelated live
elements. The selected scope preserves optional definitions and the original fix.

## Consequences

Optional commented patterns keep a slug-prefixed ID and matching URL reference.
No render, network, release, or merge behavior is added by this correction.

## Validation

The refreshed standalone SVG export suite passes 60 tests, including template-dots, live-title accessibility, and upstream shipped-asset regressions. Full policy and hosted checks are separate gates. Earlier frozen before/after controls remain in local evidence.
