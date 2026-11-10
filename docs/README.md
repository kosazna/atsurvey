# ATSurvey documentation

| Document | For |
|---|---|
| [features.md](features.md) | **what the app offers**: every feature, its status and where it is documented |
| [PLAN.md](PLAN.md) | roadmap, status, open decisions |
| [adr/0001-architecture.md](adr/0001-architecture.md) | why the system is built this way |
| [contracts.md](contracts.md) | API payloads and database schema shared by all parts |
| [engine.md](engine.md) | computation methods, formulas, settings, issue codes |
| [numerics.md](numerics.md) | float64 vs Decimal, measured precision, rounding policy |
| [adjustment.md](adjustment.md) | least-squares network adjustment, statistics, blunder detection |
| [cogo.md](cogo.md) | COGO tools (inverse, polar, intersections, resection, area, transformation, chainage) and levelling |
| [science-roadmap.md](science-roadmap.md) | surveying tools for Greek practice: what is built, what is blocked (⛔ dependencies) |
| [parcels.md](parcels.md) | parcel area, Cadastre tolerance, subdivision, merge, coverage |
| [dgm.md](dgm.md) | Διάγραμμα Γεωμετρικών Μεταβολών: Cadastre spec, builder, pre-submission validator |
| [surfaces.md](surfaces.md) | TIN, breaklines, contours, volumes, profiles |
| [setout.md](setout.md) | batch setting out, as-staked check, road axis (clothoids), vertical profile |
| [analysis.md](analysis.md) | network pre-analysis (precision, reliability) |
| [instruments.md](instruments.md) | levelling network adjustment, instrument checks |
| [coords.md](coords.md) | coordinate systems: ΕΓΣΑ87, UTM, TM3, Hatt, HEPOS |
| [formats.md](formats.md) | supported instrument files and how to export them |
| [validation.md](validation.md) | validating against the reference Excel workbooks |
| [api.md](api.md) | engine API endpoints, auth, plans, configuration |
| [supabase.md](supabase.md) | database, auth, storage, billing webhook, tests |
| [web.md](web.md) | web app structure, data layer, demo mode, build |
| [design-system.md](design-system.md) | tokens, typography (IBM Plex Sans), visual rules |
| [local-setup.md](local-setup.md) | **run the full app on your laptop** (Docker + local Supabase) and what to test |
| [development.md](development.md) | local setup, commands, tests, CI, conventions |
| [security.md](security.md) | threat model, controls by layer, audit findings, operational checklist |
| [deploy.md](deploy.md) | going live: Supabase, Hetzner, Cloudflare Pages, checklist |
