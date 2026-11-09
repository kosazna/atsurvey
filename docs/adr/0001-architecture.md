# ADR 0001 — Architecture of the web platform

Status: accepted · 2026-11-09

## Context

The 2020 prototype was a pandas/PyQt desktop tool with pickled projects. The product is now a
paid web app for Greek surveyors with projects, accounts and exports. Constraints: solo developer
who knows Python, Supabase (hosted, EU) for auth/data, an existing Hetzner VM, top-tier UX.

## Decisions

1. **Pure-Python engine, no pandas.** The calculation core (`engine/`) depends only on pydantic and
   the standard library; numeric work is small (hundreds of legs) so plain floats are clearer and
   exact. Export libraries are optional extras. The engine could later run in the browser (Pyodide)
   or a desktop shell unchanged.

2. **Directions, not angles, in the data model.** Observations store the horizontal *circle
   reading*. The engine forms angles from directions, averages faces/rounds and re-occupations, and
   orients detail setups on every known target. Users never need a zeroed backsight, and
   instrument files map 1:1 to the model.

3. **Radians and metres internally;** units are converted only at the edges (parsers, UI, exports).

4. **Stateless engine API; the browser persists through Supabase.** *Change from the original
   plan* (API reading the database). Reasons:
   * live recomputation while editing needs a round trip that does not wait on database reads/writes;
   * the API holds no database credentials (smaller blast radius); it only verifies the user's JWT
     and asks Supabase for the plan with that same JWT, so RLS still applies;
   * runs are saved with `save_computation_run`, which stores the engine version and the input hash
     returned by the API, so any saved result is reproducible.
   The engine still runs server-side, so paid exports cannot be bypassed.

5. **Workspace scoping from day one.** Every row belongs to a workspace (personal by default), so
   teams can be added without a migration of the data model.

6. **Billing through a merchant of record (Paddle).** Paddle handles EU VAT and invoices; the
   webhook only writes a `subscriptions` row. Plan checks: database trigger (project limit) and API
   (`/v1/export`).

7. **Typst for the PDF report.** Fast, deterministic, embedded fonts with Greek coverage, no
   headless browser on the server.

8. **DXF first, DWG later.** `ezdxf` writes clean R2013 DXF which every CAD opens; DWG needs a
   licensed converter (ODA) and is deferred.

## Consequences

* Two deployables (static web app, API container) plus hosted Supabase.
* Tolerance defaults are generic placeholders until set to the user's specification (see PLAN).
* Parsers are verified with synthetic round-trips; real instrument files must be added as fixtures.
