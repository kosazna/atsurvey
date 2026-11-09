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
