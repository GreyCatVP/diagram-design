# Steps

**Best for:** a short, ordered sequence of stages where the order is the claim and each stage needs a number, a compact visual cue, a title, and one brief explanation. Use it for methods, playbooks, onboarding paths, launch checklists, and “how it works” explainers.

Prefer **Timeline** when spacing encodes real elapsed time, **Flowchart** when the route branches, **Swimlane** when ownership and handoffs matter, and **Process** when each stage must expose actors, tools, or input/output payloads. Steps has one rail, no branches, no time scale, and no actor lanes.

---

## 1. Inputs

```yaml
steps:                         # 3..7, left to right
  - number: "01"
    title: "Frame"
    description: ["Define the decision", "and its success signal"]
    icon: file                 # optional; from primitive-icons.md
  - number: "02"
    title: "Research"
    description: ["Gather evidence from", "customers and operators"]
    icon: users
  - number: "03"
    title: "Synthesize"
    description: ["Turn observations into", "one testable direction"]
    icon: search
    focal: true
  - number: "04"
    title: "Decide"
    description: ["Commit the scope and", "name the trade-offs"]
    icon: database
  - number: "05"
    title: "Ship"
    description: ["Release, measure, and", "feed learning forward"]
    icon: container
dark: false
```

Rules:

- `steps` contains 3–7 entries. Fewer than three is a list; more than seven needs grouping or a second diagram.
- Exactly one step is `focal: true`. It is the decision, transformation, or risk the figure exists to emphasize.
- `number` is two digits for fewer than 100 steps (`01`, `02`, …) so the rail scans evenly.
- `description` is one or two short lines, each no longer than 26 characters at the standard ramp. Rewrite rather than shrink.
- `icon` is optional and must come from [`primitive-icons.md`](primitive-icons.md). Omit icons from every step if a coherent set is unavailable; never mix line icons, emoji, and brand marks.

---

## 2. Layout grammar

The canonical `doc-wide` canvas is `1280×720`. All structural coordinates sit on the 4px grid.

```text
outer_x          = 80
rail_y           = 240
rail_h           = 48
n                = len(steps)
usable_w         = 1280 - 2 * outer_x
stage_w          = min(224, 4 * floor(usable_w / (4 * n)))
content_w        = n * stage_w
start_x          = (1280 - content_w) / 2
stage_x(i)       = start_x + i * stage_w
stage_cx(i)      = stage_x(i) + stage_w / 2
medallion_cy     = rail_y + rail_h / 2
medallion_r      = 36
number_y         = 164
number_rule_y    = 184..220
title_y          = 360
description_y    = 388, 408
legend_rule_y    = 600
legend_y         = 636
```

This yields a 224px stage for 3–5 steps, 184px for 6, and 160px for 7. Keep `stage_w` on the 4px grid, center the combined rail, and preserve at least 24px between description columns. If copy does not fit the narrower six- or seven-stage columns, widen the canvas or rewrite the copy; do not reduce the type ramp.

### Rail

- Draw one contiguous horizontal rail from `stage_x(0)` to `stage_x(n-1) + stage_w`.
- Each stage owns one `stage_w × 48` segment. Alternate `ink @ 0.05` and `ink @ 0.09` fills to make the segmentation visible without introducing a series palette.
- The focal segment uses `accent-tint` with a 1px `accent` top and bottom rule.
- The rail itself expresses order. Do not add arrows between adjacent stages; they duplicate the layout.

### Number and guide

- Number: `{eyebrow}` role, 8px, weight 600, letter-spacing `0.14em`, centered at `stage_cx(i)`.
- Guide: 1px vertical rule from `y=184` to `y=220`, `rule-solid`; focal guide uses `accent`.
- The number is `muted` by default and `accent` for the focal step.

### Icon medallion

- Circle center `(stage_cx(i), 264)`, radius 36.
- Draw an opaque `paper` circle first so the rail does not show through, then a 1px outline.
- Default outline and icon use `ink`; focal outline and icon use `accent` and the circle may use `accent-tint`.
- Place one 24×24 primitive at `(stage_cx(i)-12, 252)`. Icons are decorative (`aria-hidden="true"`); the accessible name comes from the SVG title and description.

### Copy block

- Title: `{node-name}` role, 12px, weight 600, centered at `y=360`.
- Description: `{sublabel}` role, 9px, centered, at most two lines at `y=388` and `y=408`.
- Titles use `ink`; descriptions use `muted`. The focal title may use `accent`; the description remains `muted`.

---

## 3. Focal and color rules

One step is focal. Treat its number, guide, rail segment, medallion outline/icon, and title as one visual unit. All remaining steps stay neutral.

Do not assign a different hue to every step. The familiar five-color infographic treatment turns sequence into a legend-reading task and conflicts with the global 1–2 accent rule. If stages genuinely encode categories rather than order, use a chart or another type whose color carries data.

---

## 4. Legend

Use a bottom strip only when the focal state needs explanation. The canonical examples show:

- neutral outlined medallion — `Stage`
- accent outlined medallion — `Focal stage`
- italic note — `Equal spacing shows order, not elapsed time.`

If the title or subtitle already names the focal stage and the distinction is obvious, remove the legend.

---

## 5. Reproducibility checklist

1. Step count is 3–7 and exactly one entry is focal.
2. Step origins, segment widths, medallion centers, and copy anchors derive from §2.
3. The rail is contiguous; there are no gaps, arrowheads, or diagonal connectors.
4. Every medallion has an opaque paper mask beneath its outline.
5. Every step either has one icon from `primitive-icons.md` or all icons are omitted.
6. Titles stay at 12px and descriptions at 9px; long copy is rewritten, not shrunk.
7. The focal step is the only accent-bearing stage.
8. The SVG uses the accessible SVG contract and the wrapper owns horizontal scrolling.

---

## 6. Anti-patterns

- Rainbow stage bands with no categorical meaning.
- Using Steps for dated events, branching decisions, actor handoffs, or feedback loops.
- Paragraphs under each stage; two short lines is the ceiling.
- A different icon style per stage, emoji mixed with line icons, or icons that repeat the title without adding recognition.
- Arrowheads between every adjacent segment. The left-to-right rail already says “next.”
