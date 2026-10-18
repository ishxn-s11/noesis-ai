# NOESIS AI — API Reference

Base URL: `http://localhost:8000/api` (interactive OpenAPI at `/docs`,
machine schema at `/openapi.json`). All endpoints except
`/auth/register` and `/auth/login` require `Authorization: Bearer <JWT>`.

## Auth (`/api/auth`)

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Register user + tenant (first user becomes admin) |
| POST | `/auth/login` | Exchange credentials for a JWT |
| GET | `/auth/me` | Current identity |

## Research (`/api`)

| Method | Path | Description |
|---|---|---|
| POST | `/projects` | Create research project |
| GET | `/projects` | List projects |
| GET | `/projects/{project_id}` | Project detail |
| POST | `/projects/{project_id}/sessions` | Create resumable session |
| GET | `/sessions/{session_id}` | Session + state + messages + jobs |
| POST | `/sessions/{session_id}/run` | Start (or resume) research run |
| GET | `/sessions/{session_id}/timeline` | Agent activity timeline with evidence |
| GET | `/sessions/{session_id}/artifacts` | Artifacts produced in session |
| GET | `/artifacts/{artifact_id}/download` | Download artifact (tenant-scoped) |
| GET | `/jobs/{job_id}` | Job status (polling alternative to SSE) |
| GET | `/jobs/{job_id}/events` | Live agent activity (SSE stream) |

## Memory (`/api/memory`)

| Method | Path | Description |
|---|---|---|
| GET | `/memory/episodic` | List/search experiment records |
| GET | `/memory/episodic/{memory_id}` | Episodic record detail |
| POST | `/memory/semantic` | Write knowledge (established needs sources) |
| GET | `/memory/semantic` | Search/list semantic knowledge (latest versions) |
| GET | `/memory/semantic/{memory_id}` | Knowledge item + version chain |
| POST | `/memory/semantic/{memory_id}/promote` | Versioned status promotion |
| POST | `/memory/procedural` | Save workflow (starts `pending`) |
| GET | `/memory/procedural` | List procedures (approved first) |
| POST | `/memory/procedural/{memory_id}/approve` | Approve (requires execution evidence) |
| GET | `/memory/context` | FalkorDB context subgraph for the tenant (nodes+edges; `available:false` = graph down, not "no context") |

## Simulations & labs (`/api`)

| Method | Path | Description |
|---|---|---|
| POST | `/simulations` | Queue an isolated REBOUND N-body run |
| GET | `/simulations/{job_id}/result` | Snapshots + conservation diagnostics |
| GET | `/simulations/{job_id}/result.png` | Trajectory plot PNG |
| POST | `/experiments` | Create + queue parameter-sweep experiment |
| GET | `/experiments/{experiment_id}` | Sweep results + validations |
| GET | `/experiments` | List experiments |
| POST | `/labs/stellar` | Stellar model + HR artifact; `source:"analytic"` (default, simplified) or `source:"parsec"` (published PARSEC v1.2S tracks, optional `age_yr` and `metallicity_z` — bundled grids at Z=0.001/0.014 with log-Z interpolation in between, returns provenance + track curve) |
| GET | `/labs/stellar/tracks` | Track browser: all full-grid evolutionary paths (`?metallicity_z=`, grid or interpolated Z) — 29 tracks with ZAMS/MS-end markers + provenance (auth required) |
| POST | `/labs/stellar/tracks.png` | Track-browser HR diagram rendered as a PNG artifact (`?metallicity_z=`) for download/export (auth required) |
| GET | `/labs/stellar/isochrone` | Fixed-age isochrone derived from the track grid (`?age_yr=`, `?metallicity_z=`): each grid track interpolated at that age, points ordered by mass; masses whose tracks do not span the age are omitted and listed in `excluded_masses_msun` — never extrapolated (auth required) |
| POST | `/labs/cosmology` | Distance ladder + expansion history |
| POST | `/labs/cosmology/mcmc` | H0/Om0 posterior (emcee UQ) |
| POST | `/labs/fits` | Inspect an uploaded FITS file |
| POST | `/labs/archive` | Query a documented public archive API (`exoplanet_archive`, `gaia`, `vizier`, `simbad`, `arxiv`, `apod` — `apod` serves real captured NASA imagery: APOD API primary, transparent NASA Image Library fallback while APOD returns placeholders; 6 h disk cache) |
| POST | `/labs/transform` | ICRS/Galactic coordinate transform + round-trip |
| POST | `/labs/crossmatch` | Cone cross-match two catalogs |
| POST | `/labs/lightcurve` | Photometric time-series stats + periodogram |

## Agents (`/api/agents`)

| Method | Path | Description |
|---|---|---|
| GET | `/agents` | Agent definitions: prompts, tools, memory policy |
| GET | `/agents/runs/{session_id}` | Coordination graph for a session |

Errors: structured `{code, message, detail}` JSON; 401 missing/invalid token,
403 cross-tenant access, 409 state-version conflict, 422 validation.