# Numerical precision and rounding policy

## Short answer: binary floats (IEEE-754 float64), not `Decimal`, and it is proven safe

* **Decimal cannot do the maths.** Every coordinate passes through sin, cos and atan2. Python's
  `Decimal` has no trigonometry, and trigonometric results are irrational, so they have no exact
  decimal value anyway. `Decimal` makes base-10 *money* exact. It adds nothing to geodesy except
  cost.
* **float64 has the precision to spare.** It carries ≈ 15.9 significant digits. A ΕΓΣΑ87 northing
  such as 4 699 999.991 m uses 10 of them down to the millimetre, which leaves a resolution of
  ≈ 1 nm. A total station measures to ≈ 1 mm, roughly a million times coarser.
* **Measured, not assumed.** `engine/tests/test_precision.py` recomputes long traverses
  independently in **50-significant-digit Decimal** arithmetic (sin/cos/π from the recipes in the
  Python documentation), from exactly the same input numbers, and compares:

| Location | Traverse length | max \|float64 − Decimal(50)\| |
|---|---|---|
| Attica (E 476 000, N 4 205 000) | 30–33 km, 60 legs | 1.6 – 4.0 nm |
| Extreme ΕΓΣΑ87 (E 900 000, N 4 700 000) | 30–33 km, 60 legs | 1.6 – 4.0 nm |
| West/south (E 101 000, N 3 850 000) | 30–33 km, 60 legs | 1.2 – 1.9 nm |

The test fails if any deviation exceeds 1 µm. A closed 60-leg, ~24 km loop computed from exact
geometry closes to < 0.1 µm, and to < 10⁻¹² rad in angle.

## What actually protects measurement quality

| Risk | Control |
|---|---|
| Rounding intermediate values (the 2020 code rounded at every step) | Full precision throughout; rounding **only** for display and export |
| Cancellation when summing many legs | `math.fsum` (exactly rounded, compensated summation) for traverse lengths, ΣΔX, ΣΔY, means of rounds and forward/backward legs, circular means |
| Large-coordinate products (areas at ΕΓΣΑ87 magnitudes) | Shoelace formula on coordinates relative to the first vertex (1 m² square at E 900 000 is exact to 10⁻⁹ m²) |
| Angle wrap-around (399.9999ᵍ vs 0.0001ᵍ) | Circular means and differences (`wrap_pi`), never plain averages of directions |
| Transport between browser, API and database | JSON numbers use the shortest round-trip representation; JavaScript and PostgreSQL `float8` are the same IEEE-754 double. A result round-trips **bit for bit** (tested) |
| Unit conversions (gon/deg/DMS ↔ rad) | Round-trip error < 10⁻⁹ of the unit (tested for 2 000 random values per unit) |
| Auditability of the raw input | Original instrument files are stored unchanged in Supabase Storage. Every run stores the engine version and a SHA-256 hash of its input |

## Rounding policy

* The engine never rounds. Results carry full float64 values.
* Display, PDF, CSV and Excel round to the number of decimals the user chooses (default 3 for
  metres, 4 for gon, 1 for cc). Python (`format`, `round`) and JavaScript (`toFixed`) round the
  exact binary value **correctly**: ties to even, on the true value.
  ΕΓΣΑ87 values such as 4205333.1875 are not exactly representable in binary, so in practice the
  printed digits are simply the correctly rounded true value.
* Excel receives numbers (not text) rounded to the chosen decimals, so formulas in the user's own
  sheets work on exactly what is printed.
* Angles typed by the user in gon are stored in radians. Converting back reproduces the typed
  value to within 10⁻¹² gon, far below the 4th decimal that is displayed.

## Where Decimal *would* be right

Prices, invoices and VAT. These are handled by Paddle (merchant of record), not by this codebase.
