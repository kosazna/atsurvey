# Excel validation cases

One JSON file per workbook case, picked up automatically by `test_excel_cases.py`:

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

Angles inside `input` are radians, as everywhere in the engine. `scripts/excel_to_case.py`
(added together with the first workbook) converts a workbook into this format.
