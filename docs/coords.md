# Coordinate systems (Συστήματα)

Code: [`engine/src/atsurvey/core/coords/`](../engine/src/atsurvey/core/coords) (pure Python, no
PROJ at runtime), API [`routers/coords.py`](../api/src/atsurvey_api/routers/coords.py), web
`tools/coords/` (group «Συστήματα»), client `web/src/lib/coordsApi.ts`.

The tools convert point lists between the systems a Greek surveyor meets and report the scale
factor, meridian convergence and zone of a point. **Projection maths is exact** (nanometre level,
proven against PROJ). **Datum changes are labelled with their accuracy**: the generic EPSG shifts
are metre-class; the official HEPOS transformation (≈ 8 cm) runs only where its grids are installed.

## Systems

| id | Datum / ellipsoid | Definition | Source |
|---|---|---|---|
| `egsa87` | GGRS87 / GRS80 | TM, λ₀ 24°, k₀ 0.9996, FE 500 000, FN 0 | EPSG:2100 (checked against the EPSG database in the tests) |
| `ggrs87_geo` | GGRS87 / GRS80 | φ, λ | EPSG:4121 |
| `wgs84_geo` | WGS84 (≈ ETRS89 / HTRS07) | φ, λ, h | EPSG:4326 |
| `utm34`, `utm35` | WGS84 | TM, λ₀ 21° / 27°, k₀ 0.9996, FE 500 000 | EPSG:32634 / 32635 |
| `tm3_west`, `tm3_central`, `tm3_east` | Old Greek / Bessel 1841 | TM, λ₀ = −3° / 0° / +3° **from the Athens meridian**, k₀ 0.9999, FE 200 000, northings from φ₀ = 34° | see "TM3" below (secondary sources) |
| `greek_geo` | Old Greek / Bessel 1841 | φ, λ (Greenwich longitudes) | EPSG:4120 |
| `hatt` | Old Greek / Bessel 1841 | azimuthal equidistant about a sheet centre | see "Hatt" below |

Athens Observatory meridian: 23°42′58.815″ E of Greenwich (EPSG:8912, `PRIMEM["Athens",23.7163375]`
in EPSG:4815).

Point convention in the API: grid systems `x` = E, `y` = N (m); geographic systems `x` = λ,
`y` = φ in **radians**. The web app shows and accepts φ λ (latitude first) in DMS
(`37°58'45.6"`, packed `37.584560`) or decimal degrees.

## Formulas and references

* **Transverse Mercator** (ΕΓΣΑ87, UTM, TM3): Krüger n-series to 6th order, C. F. F. Karney,
  "Transverse Mercator with an accuracy of a few nanometers", *J. Geodesy* 85 (2011) 475–485,
  eqs. 7–36, with Newton iteration for the inverse. Gives the point scale factor k and the
  meridian convergence γ (bearing of grid north clockwise from true north; positive east of the
  central meridian), eqs. 25–28. Same algorithm as GeographicLib and PROJ.
* **Geodesic** (for Hatt): Vincenty (1975), *Survey Review* 23(176) 88–93, direct and inverse.
* **Geodetic ↔ geocentric**: EPSG Guidance Note 7-2 (method 9602), fixed-point iteration on φ.
* **Tissot indicatrix** of non-conformal projections (Hatt): numerical Jacobian, closed-form 2×2
  SVD (Snyder 1987, USGS PP 1395 §4). Checked against the analytic TM k, γ to 1e-9.
* **Combined factor** in "Στοιχεία σημείου": k · R/(R + h), R = √(M N) at φ, h = H + N.

### Datum shifts

```
greek (Bessel) ── EPSG:1891 ── ggrs87 (GRS80) ── EPSG:1272  or  HEPOS ── wgs84 / HTRS07
```

| Edge | Method `approximate` | Method `official` |
|---|---|---|
| ggrs87 ↔ wgs84 | EPSG:1272 geocentric translation ΔX −199.87, ΔY 74.79, ΔZ 246.62 m (the `+towgs84` of EPSG:2100 and of the web map). EPSG states 1 m; against HEPOS it is 0.2–1.5 m off across Greece (measured at 8 points), so the tool reports **1.5 m** | HEPOS HTRS07 ↔ ΕΓΣΑ87, ≈ 8 cm, only if the grids are installed, otherwise `COORD_HEPOS_UNAVAILABLE` |
| greek ↔ ggrs87 | EPSG:1891 geographic offsets Δφ −5.86″, Δλ +0.28″, **5 m** (EPSG: "More accurate polynomial transformations … are available from the Military Geographic Service") | Hatt → ΕΓΣΑ87 per-sheet ΟΚΧΕ polynomial (user-entered or from the sheet table); TM3 and reverse direction: `COORD_NO_OFFICIAL_SHIFT` |

An approximate result carries `approximate: true`, `accuracy_m`, the issue `COORD_APPROXIMATE`
and, in the web app, a prominent warning («όχι για κτηματολογικές εργασίες»). Old-datum shifts
also raise `COORD_OLD_DATUM_LOCAL_FIT`: for survey work, fit a local Helmert/affine
transformation on common points with the existing **Μετασχηματισμός** tool.

### HEPOS (official HTRS07 ↔ ΕΓΣΑ87)

Kotsakis, Katsambalos, Gianniou, «Μοντέλο Μετασχηματισμού Συντεταγμένων μεταξύ HTRS07 και
ΕΓΣΑ87», ΚΤΗΜΑΤΟΛΟΓΙΟ Α.Ε. / ΑΠΘ (2008), implemented in `coords/hepos.py`:

1. 7-parameter similarity, coordinate-frame convention: tx 203.437, ty −73.461, tz −243.594 m,
   εx −0.170″, εy −0.060″, εz −0.151″, δs −0.294 ppm.
2. (φ′, λ′) on GRS80 → TM87 (E′, N′).
3. δE, δN by bilinear interpolation of the 2 km grids `dE_2km_V1-0.grd`, `dN_2km_V1-0.grd`
   (cm, 408 × 422 nodes from E 41 600 / N 1 845 619) at the point's **TM07** position (TM87 with
   FN −2 000 000) from the original HTRS07 coordinates; E = E′ + δE, N = N′ + δN.
4. Inverse as specified: parameters negated, corrections interpolated at the TM07 position and
   subtracted (not iterated, like the official software).

**The grids are not in the repository**: hepos.gr terms forbid redistribution without written
consent. A server whose operator holds the files sets `ATSURVEY_HEPOS_GRID_DIR` to the folder
containing both `.grd` files; the engine loads them lazily on first use. Without it the
"official" method answers `COORD_HEPOS_UNAVAILABLE`. Kastelorizo (its own 3-parameter model) is
not implemented; points outside the grid fail individually.

Validation: `engine/tests/test_coords_hepos.py` reproduces the official worked example
(pp. 8–12) step by step without grids (similarity to 1 mm, TM07 position, TM87 before the grid,
inverse steps), tests the grid reader and bilinear interpolation on synthetic grids, and runs the
full example (final E 566 296.538, N 4 529 332.307; inverse φ 40°54′53.90608″,
λ 24°47′20.59229″) to 1 mm when `ATSURVEY_HEPOS_GRID_DIR` is set — verified locally with the
official files; skipped in CI.

## TM3 — definition and uncertainty

Used in the 1980s by ΥΠΕΧΩΔΕ (ΕΠΑ urban plans). Sources agree on: Transverse Mercator, Old Greek
datum, **Bessel 1841**, k₀ = 0.9999, FE = 200 000 m, three 3° zones with central meridians
**−3°, 0°, +3° from the Athens meridian**, northings counted from the parallel φ₀ = 34° (N₀ = 0):

* Σ. Κατσουγιαννόπουλος, Γ. Βέργος, «Εφαρμογές GPS», ΑΠΘ (2004), §5.2;
* Α. Ντέρης, Μεταπτυχιακή διατριβή, ΑΠΘ (2014), §2.4.2, after Φωτίου (2007);
* Κακογιάννου, ΑΠΘ, §1.4.2.2.2, after Φωτίου & Λιβιεράτος (2000), Νάκος (2010).

Open points, **verify with one real TM3 control-point pair** before relying on it: one source
table lists the Hayford ellipsoid; other snippets mention 21°/24°/27° Greenwich or FE 500 000;
"northings from 34°" is implemented as PROJ `+lat_0=34` (subtracting k₀·M(34°)); subtracting
M(34°) without k₀ would shift northings by ≈ 376 m, which a single known point would reveal.
There is no official TM3 → ΕΓΣΑ87 transformation: use EPSG:1891 (5 m, indicative) or a local
Helmert/affine fit.

## Hatt — definition and uncertainty

Oblique **azimuthal equidistant** projection of the Bessel ellipsoid on the plane tangent at the
sheet centre T₀(φ₀, λ₀): x = S·sin α (east), y = S·cos α (north), S and α the geodesic distance
and azimuth from T₀ (Κατσουγιαννόπουλος & Βέργος 2004 §5.2.1; Ντέρης 2014 §2.3). ≈ 130 sheets of
30′ × 30′, centres at whole degrees + 15′ / 45′, longitudes from the Athens meridian. The Greek
textbooks evaluate it with series valid to ≈ 40 km; the engine uses the exact geodesic, i.e. the
same definition as PROJ `+proj=aeqd` on the ellipsoid (agreement < 1 µm in the tests). Points
more than 40 km from the centre raise `COORD_HATT_FAR`.

Uncertain: the axis naming in some documents (x/y swapped), and how far the textbook series
differ from the exact formula at the sheet corners (expected ≪ 1 cm; not verified against an
official table).

**Sheet table and polynomials (dependency).** The official ΓΥΣ/ΟΚΧΕ tables («Πίνακες συντελεστών
μετατροπής συντεταγμένων … από το Σύστημα HATT στο Σύστημα ΕΓΣΑ'87», ΟΚΧΕ 1995) give per sheet the
centre and a 2nd-degree polynomial
`E = A0 + A1·x + A2·y + A3·x² + A4·y² + A5·x·y` (N likewise with B), quoted accuracy 10–15 cm,
cartographic use. Hooks:

* `hatt.HATT_SHEETS` (empty): a sheet code raises `COORD_HATT_TABLE_MISSING` until it is loaded.
  Store coefficients per sheet id (sheets sharing a centre have different A0/B0).
* The user may type the 12 coefficients of their sheet (A0…A5, B0…B5, x, y in metres; term order
  from secondary sources, not checked against the booklet) with method "official": Hatt → ΕΓΣΑ87
  then runs grid to grid through the polynomial. The reverse direction is refused.

## Heights

`height_in` / `height_out`: ellipsoidal h or orthometric H. H passes through any conversion
unchanged; h follows the datum shift. Changing kind needs a **constant** geoid undulation N (m)
relative to the ellipsoid of the side whose heights are ellipsoidal (h = H + N,
`COORD_CONSTANT_GEOID`; missing N → `COORD_GEOID_REQUIRED`). Valid only locally. Without
heights a datum shift assumes h = 0 on the source ellipsoid, like PROJ; a WGS84 → ΕΓΣΑ87 → WGS84
round trip without heights then differs by 1–2 mm (with ellipsoidal heights it is exact).

## API

| Endpoint | Body | Result |
|---|---|---|
| `POST /v1/coords/convert` | `src`, `dst`, `points` (1–10 000, finite, \|x\|,\|y\| ≤ 2·10⁷), `src_hatt` / `dst_hatt` (`lat0`, `lon0` rad + `meridian` athens/greenwich + optional 12 `coefficients`, or `sheet`), `datum_method` approximate/official, `height_in`, `height_out`, `geoid_undulation` (±150 m) | `points` (x, y null for a failed point), `datum_shift` labels, `approximate`, `accuracy_m`, `issues` |
| `POST /v1/coords/point-info` | `system`, `point`, `hatt`, `height_kind`, `geoid_undulation` | φ, λ (and λ from Athens), E N, `scale_factor` (conformal), `scale_min`/`scale_max`, `convergence` (rad), `elevation_factor`, `combined_factor`, `utm_zone`, `tm3_zone`, `inside_zone`, `issues` |

Both require `require_compute` (signed-in unless anonymous compute is enabled). Coded failures
return 422 `{"detail": {"code", "message", "params"}}`; other invalid input 422 with a message.

## Issue codes

| Code | Severity | Meaning |
|---|---|---|
| `COORD_APPROXIMATE` | warning | generic EPSG datum shift used (`accuracy_m`) |
| `COORD_OLD_DATUM_LOCAL_FIT` | warning | Old Greek datum involved: fit common points |
| `COORD_OUTSIDE_ZONE` | warning | points beyond the zone (± ½° tolerance), aggregated |
| `COORD_POINT_FAILED` | error | points that could not be converted (e.g. degrees typed as radians, outside the HEPOS grid), aggregated |
| `COORD_HATT_FAR` | info | > 40 km from the Hatt sheet centre |
| `COORD_CONSTANT_GEOID`, `COORD_GEOID_ASSUMED_ZERO` | info | height handling |
| `COORD_HEPOS_UNAVAILABLE`, `COORD_NO_OFFICIAL_SHIFT`, `COORD_HATT_TABLE_MISSING`, `COORD_HATT_ORIGIN_REQUIRED`, `COORD_GEOID_REQUIRED` | 422 | request cannot be served |

## Validation evidence

| Check | Result | Test |
|---|---|---|
| ΕΓΣΑ87, UTM 34/35, TM3 (3 zones) vs PROJ (`algo=poder_engsager`), 500 random points each over Greece | < 0.1 mm (observed ≈ 3 nm) | `test_coords_projections.py` |
| ΕΓΣΑ87 vs the EPSG:2100 definition from the PROJ database | < 0.1 mm | idem |
| Ordnance Survey published TM example (Airy, φ₀ = 49°) | 1 mm (publication rounding) | idem |
| k and γ vs PROJ `get_factors` | 1e-10 / 1e-8° | idem |
| TM round trip grid → φλ → grid | < 1 µm, φλ < 1e-12 rad | idem |
| Hatt vs PROJ `aeqd` on Bessel, 3 sheet centres, ±30′ | < 10 µm (observed 0.35 µm) | idem |
| Vincenty vs PROJ `Geod` | 1 µm, 1e-9° | idem |
| WGS84 → ΕΓΣΑ87 vs PROJ EPSG:4326 → 2100; Greek → GGRS87 vs EPSG:4120 → 4121; TM3 → ΕΓΣΑ87 chain | < 0.1 mm | `test_coords_convert.py` |
| HEPOS official worked example | 1 mm (all steps) | `test_coords_hepos.py` |
| 10 000 points | ≈ 0.1–0.2 s | `test_coords_convert.py` |

## Limitations and dependencies

* **HEPOS grids**: licence for server use (hepos.gr terms); until then "official" is
  unavailable on hosted servers. Kastelorizo not implemented.
* **Geoid**: no official model available (the HEPOS TT geoid is embedded and its EULA forbids
  extraction); only a constant N.
* **Hatt sheet table / ΟΚΧΕ polynomials**: not bundled; data and licence from ΓΥΣ/ΟΚΧΕ. Term
  order of the coefficients to confirm against the booklet.
* **TM3**: definition from secondary sources; confirm with a real control-point pair.
* ED50 / UTM (ΓΥΣ military) is not offered.
