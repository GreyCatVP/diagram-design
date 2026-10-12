# Export review follow-up (PR #321)

## Context

Blanket parent RGBA preservation avoids alpha inheritance changes but leaves safely inherited parent paint unusable by strict SVG importers.

## Decision

Normalize a parent when descendants inherit its paint; retain the conservative fallback for descendant paint overrides or unresolved CSS opacity. Keep numeric opacity combination and inert-content protection. Restore the export recipe as a call to the packaged helper.

Integrate current upstream main without rewriting published history or changing
package versions relative to upstream.

## Alternatives

Keeping the old candidate preserves the reported regression. Blanket conversion
or flattening conditional CSS changes browser behavior. Preserve the relevant
contracts and use narrow conservative fallback where resolution is uncertain.

## Consequences

The correction preserves the existing export interface. External font sources in
normal font mode retain their authored declaration; system-font mode retains its
existing behavior. No network validation, release or deployment is performed.

## Validation

The new review regression fails before correction and passes afterward. All 34
standalone SVG export tests pass, including shipped-asset controls. Raw local
logs record the frozen failure and candidate result. Complete repository gates
and hosted CI are separate checks and are not claimed by this scoped result.
