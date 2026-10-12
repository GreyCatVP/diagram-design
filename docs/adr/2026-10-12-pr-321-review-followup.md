# Export review follow-up (PR #321)

## Context

The published candidate `7838453e57a00680ec101157f8d112ba7f17ed87` preserves parent RGBA whenever any page CSS rule declares the paint property. The maintainer's unrelated `.paint { fill:#000 }` reproduction therefore stays RGBA although current main normalizes the unpainted child case. Current main also includes export batch #411 and stricter channel/alpha clamping and executable recipe checks.

## Decision

Integrate upstream `eb23fba57faaeea8ab331b4dd9235ed01ae18558` (including export batch `09c1428`) and retain its manifests. Exclude simple CSS selectors whose final tag/class/ID compound cannot target either the painted element or its descendants. Preserve RGBA for possible paint overrides, unsupported selector syntax, CSS opacity and independently inherited presentation opacity. Clamp channels and alpha consistently with upstream, and combine existing numeric opacity without duplicate attributes.

Keep step 7 a complete executable recipe, synchronized with the helper, including conservative CSS handling and inert comment/CDATA protection. Tests execute the recipe against clamping, unrelated page paint, child paint override and existing opacity cases.

## Alternatives

Ignoring every stylesheet paint rule would change alpha when CSS overrides child or parent paint. Keeping the blanket guard leaves the maintainer reproduction unnormalized. A full CSS cascade engine is outside this dependency-free helper's scope; unknown selector syntax remains conservative.

## Consequences

Unrelated simple page CSS no longer blocks safe presentation paint normalization. Possible CSS overrides retain their original RGBA alpha. The export interface and current upstream package versions remain unchanged. Unsupported selector syntax can still conservatively prevent conversion.

## Validation

The new unrelated-page-paint regression fails on the frozen published head and passes on frozen current main. The integrated candidate passes all 61 standalone SVG export tests, including inherited and overridden paint, CSS opacity, clamping, inert-content and shipped-asset controls. Export wait tests skip because Playwright is unavailable in the system Python; no browser-render claim is made. Raw comparison and candidate logs are local evidence. Full repository policy and hosted CI are separate gates.
