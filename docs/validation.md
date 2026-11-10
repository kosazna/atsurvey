# Validation against the reference Excel workbooks

The existing Excel workbooks are the reference users already trust. Before launch, the engine
must reproduce them to **0.1 mm / 0.1 cc**, or the difference must be explained and recorded.

## Case format

One JSON file per case in `engine/tests/fixtures/excel/`, picked up automatically by
`engine/tests/test_excel_cases.py`:

```jsonc
{
  "source": "Afidnes.xlsx / sheet 'Όδευση 1'",
  "input": { /* ProjectInput: control_points, setups, traverses, settings */ },
  "expected": {
    "points": { "S1": [476611.203, 4205290.118, 195.772] },     // X, Y, Z (Z may be null)
    "traverses": {
      "T1-T2-S1-S2-S3-T3-T4": { "angular_cc": -12.0, "wx": -0.001, "wy": 0.005, "wz": 0.0 }
    }
  },
  "tolerance": { "xy_m": 0.0001, "z_m": 0.0001, "angular_cc": 0.1, "misclosure_m": 0.0001 }
}
```

Angles inside `input` are radians. A converter (`scripts/excel_to_case.py`) will be written
against the actual workbook layout.

## Procedure

1. Convert each workbook (or each traverse sheet) into a case.
2. Choose the reduction settings that match how the workbook computes. Legacy workbooks most
   likely use `scale_mode="traverse_mean"` and `elevation_mode="traverse"`; check whether they
   apply curvature and refraction and which earth radius they use.
3. Run `uv run pytest engine/tests/test_excel_cases.py -v`. Every failure lists the point and the
   difference.
4. Classify each difference as a workbook error, an engine error or a convention difference, and
   note it in the case's `source` field. Fix engine errors with a regression test.
5. Cross-check two cases with an independent tool before treating the workbook as the reference.

## Results (2026-11-10, first batch of workbooks)

Cases are generated with `scripts/excel_cases.py` (numbers only; the workbooks are not stored).
Each case uses the workbook's own conventions: one scale factor and one mean height per
traverse, R = 6371000 m, no curvature/refraction.

| Workbook | Case | Points | Max ΔXY | Max ΔZ | Misclosures |
|---|---|---|---|---|---|
| Κλειστή πλήρως εξαρτημένη | `closed_S5_S2` | 3 | 0.01 mm | 0.00 mm | wβ −19 cc, w 8.0 mm, wz 1.9 mm — identical |
| Ανοιχτή πλήρως εξαρτημένη | `link_TN10_TN11` | 7 | 0.00 mm | (data error, see below) | wβ +92 cc, wx −13.7 mm, wy 61.1 mm — identical |
| Ανοιχτή | `open_TN11_TN10` | 5 | 0.11 mm | 0.00 mm | — |
| Ταχυμετρική S9A / S9B | `detail_S9A`, `detail_S9B` | 53 / 65 | 1.4 / 1.6 mm | 0.5 mm | — |
| Οπισθοτομία | `test_resection_matches_reference_workbook` | 1 | < 1 µm | — | — |
| Χάραξη (angle + ground distance) | `test_stakeout_matches_reference_workbook` | 1 | angle exact, 2 µm | — | — |
| Tolerances (1/500, primary, flat) | `test_greek_tolerance_preset_matches_workbook` | — | linear 0.16771 m and angular 6 c exactly | — | — |

Remaining sub-millimetre differences are explained by the workbooks themselves:
* the closed and open sheets round the scale factor to 4 decimals and the starting azimuth to
  4 decimals of a grad;
* the detail sheets round every intermediate value (horizontal, reduced and grid distance, ΔX,
  ΔY) to the millimetre.

### Findings in the workbooks

1. **Link traverse (ανοιχτή πλήρως εξαρτημένη), leg S7–TN10.** Row 19 (TN10→S7, ΥΟ 1.547)
   contains the zenith and distance of the *opposite* shot (102.2147 g, 55.498 m). The same leg in
   the open-traverse workbook reads 97.9751 g / 55.499 m from TN10. As entered, both directions
   say "downhill". The workbook averages |ΔH| with the forward sign (`IF(J>0, AVERAGE(ABS…))`),
   which hides the contradiction. The engine averages signed values, reports `LEG_HEIGHT_FB`
   (forward/backward differ by 3.70 m) and flags the height misclosure. Heights of this case are
   therefore not compared; X/Y and all misclosures agree exactly.
2. **Levelling workbook (χωροστάθμηση).**
   * The forward/return pairing formulas reference the wrong rows (e.g. `H8` pairs the forward
     Rn→Σ22 segments with return rows 38–40, which belong to Σ27→Κ6; `H9` pairs with the empty
     row 37). The ΔH column, and the heights derived from it, are not reliable.
   * Comparing the runs correctly section by section (new double-run levelling, see
     [cogo.md](cogo.md)): Rn–Σ22 −1 mm, Σ22–Σ23 +2 mm, Σ23–Σ24 +1 mm, **Σ24–Σ25 −18 mm**,
     **Σ25–Σ26 −303 mm**, Σ26–Σ27 +2 mm. In Σ25–Σ26 the staff reading on Κ6 is 2.843 forward but
     2.544 on the return run, a 0.3 m (decimetre-digit) misread in one of the runs. The section
     must be re-measured; the data alone cannot tell which run is wrong.
3. **Tolerance table.** In the sloped-terrain rows, 1/10000 has a constant term of 0.3 m, lower
   than the 0.4 m of 1/5000 (the flat rows increase monotonically). This looks like a copy from the
   flat table. The presets reproduce the workbook as-is; please confirm against the specification.
