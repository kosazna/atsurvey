# Instrument formats

Code: [`engine/src/atsurvey/formats`](../engine/src/atsurvey/formats). `parse_file(data, filename)`
detects the format from the content and the extension. Every parser returns setups (station,
instrument height, observations in radians) plus any coordinates found in the file, which become
candidate control points.

| Format | Extensions | Angle unit | Coordinates imported |
|---|---|---|---|
| Leica GSI-8 / GSI-16 | `.gsi`, `.gs8`, `.gs16` | from each word's unit code (gon / deg / DMS / mil) | words 81–86 |
| Trimble JobXML | `.jxl` | always decimal degrees, metres | keyed-in grid points |
| LandXML (raw observations) | `.xml` | `Units/Metric@angularUnit` | `CgPoints` |
| Nikon RAW v2.00 | `.raw` | **not stated in the file**: project setting (default gon) | `UP`/`KI`/`CC` records |
| Carlson / TDS RW5 | `.rw5` | **not stated reliably**: project setting (default gon) | `OC`/`SP` records |
| CSV (incl. Greek Excel `;` + decimal comma) | `.csv`, `.txt` | project setting | `name,x,y,z[,code]` |

## Exporting from the instrument or office software

| Brand | What to export | Notes |
|---|---|---|
| Leica (TPS, Captivate, FlexLine) | **GSI-16** (or GSI-8) raw data, or **LandXML** from Leica Infinity | Native **DBX** jobs are a closed binary format and cannot be read. Export on the instrument (Data → Export → format "GSI") or from Infinity. |
| Trimble (Access, TBC) | **JobXML (.jxl)** | The native `.job` file is binary. Trimble Access: Job → Export → JobXML. TBC: Export → JobXML or LandXML. |
| Nikon / Spectra (Nivo, NPL) | **RAW** (`.raw`) | Make sure the project's angle unit matches the instrument's setting. |
| Carlson SurvCE / SurvPC, older Nikon/Sokkia via converters | **RW5** | This is the format the 2020 prototype's "Nikon" converter actually read (`OP`/`FP`/`AR`/`ZE`/`SD`/`HR`/`HI` records). |
| Anything else | CSV with columns `station, target, hz, v, sd, hi, ht, code` | Greek headers (`Στάση`, `Σημείο`, `Οριζόντια`, `Κατακόρυφη`, `Απόσταση`, `υο`, `υσ`, `Κωδικός`) are recognised. |

## Record details

**GSI.** A line is a sequence of words: 2-digit word index, 4 information characters, sign, then 8
or 16 data characters. The unit code sits in information position 6. A line with words 84–88 and
no 21 starts a new setup; lines with 21/22/31 are observations from the current setup. Point ids in
word 11 lose their zero padding.

**JobXML.** `StationRecord` (name, theodolite height) ↔ `PointRecord` with a `<Circle>` block
(`HorizontalCircle`, `VerticalCircle`, `EDMDistance`) linked by `StationID`, and target height via
`TargetID` → `TargetRecord`. Deleted records are skipped and counted.

**LandXML.** `Survey/InstrumentSetup` (`stationName`, `instrumentHeight`) with `RawObservation`
(`horizAngle`, `zenithAngle`, `slopeDistance` or `horizDistance`, `targetHeight`,
`TargetPoint@pntRef`). `CgPoint` text is "northing easting [elevation]".

**Nikon RAW.** `ST` (station, backsight, HI, backsight circle reading) and `F1`/`F2`/`SS`/`CP`/`TR`
(point, [code], HT, SD, HA, VA, time, code).

**RW5.** `LS` (HI/HR), `OC`/`SP` (coordinates N, E, EL), `BK` (backsight point and circle reading),
`SS`/`TR`/`BD`/`BR`/`FD`/`FR`/`OB` (OP, FP, AR, ZE, SD, `--code`).

## Security

XML is parsed with `defusedxml` (entity-expansion and external-entity attacks are rejected, and a
test covers it). Uploads are limited by `MAX_UPLOAD_MB` (default 20 MB) in the API.

## Status

The parsers follow the published record layouts and are verified by writing synthetic surveys in
each format, parsing them back and computing them (`engine/tests/test_formats.py`). Real files
from the field can contain firmware-specific quirks. Add samples to `engine/tests/fixtures/` as
they arrive and extend the tests.
