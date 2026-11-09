# Design system

Every screen and every generated report draws on one set of tokens, so a palette change is a
one-file edit.

## Principles

* **Modern and minimal**: whitespace over decoration, hairline borders instead of heavy shadows, no
  gradients, line icons only (lucide).
* **One accent colour, used sparingly** for primary actions, focus and the active selection.
  Everything else is a calm neutral scale.
* **Data first**: tabular figures for every number (`font-variant-numeric: tabular-nums` on the web,
  `number-width: "tabular"` in Typst), numbers right-aligned, labels muted.
* **Status by meaning, not decoration**: success / warning / danger colours appear only on tolerance
  results and issues, as small pills or text.
* **4 px spacing rhythm** (`--space-*`).

## Typography

**IBM Plex Sans** (SIL Open Font License; Latin + Greek) everywhere:

| Where | How |
|---|---|
| Web | `@fontsource/ibm-plex-sans` (400/500/600, `greek` + `latin` subsets) |
| PDF report | TTFs embedded from `engine/src/atsurvey/exports/fonts/` (rebuilt by `scripts/build_report_fonts.py`) |
| Excel | workbook default font "IBM Plex Sans" (Excel substitutes if it is not installed) |
| DXF | text style `ATS` → `IBMPlexSans-Regular.ttf` (CAD substitutes if it is not installed) |

Plex has no `ᵍ` (U+1D4D) glyph, so the grad unit is written as a small muted `g` or `gon`.

## Tokens

Source: [`design/tokens.json`](../design/tokens.json). Generated (do not edit):

* `web/src/styles/tokens.css`: CSS custom properties for light (`:root`), dark
  (`[data-theme="dark"]`) and system (`prefers-color-scheme`), mapped into Tailwind v4 via
  `@theme inline`, so classes such as `bg-surface`, `text-muted`, `border-border`, `rounded-md` and
  `shadow-sm` resolve to tokens.
* `engine/src/atsurvey/exports/theme.json`: light colours and the font, for PDF and Excel.

```bash
uv run python scripts/build_tokens.py          # regenerate after editing tokens.json
uv run python scripts/build_tokens.py --check  # CI fails if generated files are stale
```

| Group | Tokens |
|---|---|
| Surfaces | `color-bg`, `color-surface`, `color-surface-raised`, `color-surface-sunken`, `color-overlay` |
| Lines | `color-border`, `color-border-strong`, `color-focus` |
| Text | `color-text`, `color-text-muted`, `color-text-subtle` |
| Accent | `color-accent`, `color-accent-hover`, `color-accent-contrast`, `color-accent-subtle` |
| Status | `color-success`, `color-warning`, `color-danger`, `color-info` (+ `-subtle` backgrounds) |
| Map | `color-point-control`, `color-point-traverse`, `color-point-detail`, `color-traverse-line`, `color-map-bg`, `color-map-grid` |
| Type | `font-sans`, `font-mono`, `text-xs … text-3xl`, `leading-tight/normal`, `weight-regular/medium/semibold` |
| Shape | `radius-sm/md/lg/xl/full`, `shadow-sm/md/lg` |
| Space | `space-1 … space-12` (4 px steps) |
| Motion | `duration-fast/normal`, `ease-standard` |
| Layout | `sidebar-width`, `topbar-height`, `z-dropdown/overlay/modal/toast` |

The current colours are a **neutral placeholder palette**. To brand the product, change the values
in `tokens.json` (keep the names), regenerate, and check contrast (WCAG AA: 4.5:1 for text,
3:1 for UI).

## Rules for code

* No hard-coded colours, radii, shadows or font sizes in components or templates: use tokens.
* MapLibre paint properties cannot read CSS variables. The map reads resolved values with
  `getComputedStyle` and updates when the theme changes.
* Reports read `theme.json`; Typst colours are looked up by token name (`c("text-muted")`).
