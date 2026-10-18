# NOESIS AI — Limitations (actual status)

This file exists so nothing planned is mistaken for implemented.

## Implemented and verified

- Durable multi-node research orchestration with resumable jobs, retries,
  timeouts, and per-thread DB sessions. **37 backend tests pass.**
- Episodic / semantic / procedural memory with versioning, promotion gates,
  latest-version-only listings, and vector search (correlated anti-join
  filters superseded versions).
- REBOUND N-body engine: exact-finish integration (no backward overshoot),
  conservation diagnostics (energy/angular-momentum drift), ejection and
  collision guards, numerical-vs-Kepler period cross-checks.
- Parameter-sweep experiments with per-run validation; validation checks
  (conservation, Kepler pairing, cosmology cross-check, coordinate
  round-trip) all pass in the E2E run.
- Reproducible demo script `scripts/e2e_demo.py` exercising the full
  12-step scenario including session resume, memory reuse, and report
  generation with artifact download.
- Alembic migrations: 16-table autogenerate revision + PostgreSQL RLS
  policy revision, both verified with `alembic upgrade head`.
- Frontend: 9 pages, SSE live run view, type-check and production build
  green (`tsc -b --noEmit`, `vite build`).

## Simplified by design (documented in code)

- Stellar evolution: **real published tracks are integrated** — two curated
  29-track metallicity grids of the EEP-matched PARSEC v1.2S release
  (Z = 0.014 solar and Z = 0.001, both 0.1–100 M☉, Rosenfield et al.
  distribution) bundled as CSVs (4,208 + 4,205 rows) with provenance
  metadata; the Stellar Lab serves track-interpolated parameters
  (`source="parsec"`) alongside the older simplified analytic model
  (`source="analytic"`), each labeled with model fidelity, plus a track-
  browser view of the full grid (`GET /api/labs/stellar/tracks`).
  Interpolation is linear in log age, log mass and log Z (two-point Z
  interpolation between the two bundled grids; **no extrapolation in Z** —
  only two metallicities are bundled, so metallicity-dependent physics is
  coarsely sampled). ZAMS/MS-end identification uses documented proxies
  (max log g; L > 1.3 L_ZAMS). The Z = 0.001 grid was cross-checked against
  the official PARSEC CMD 3.7 interface (1 M☉ at 4.6 Gyr: 7170 K vs our
  7171 K — v1.2S low-Z tracks really are hot). MESA itself is still not run
  in-process (documented, not claimed). Regenerate with
  scripts/convert_parsec_tracks.py.
- Semantic embeddings default to a deterministic local provider; OpenAI
  embeddings require configuration.
- Agents run in a deterministic rule-based mode when no LLM provider is
  configured (`NOESIS_LLM_BASE_URL` unset). Agent "reasoning" text in that
  mode is template-generated from real tool results, never fabricated data.

## Context layer (FalkorDB)

- Implemented: `app/memory/context_graph.py`, plan-node retrieval, memory-node
  writes, `GET /api/memory/context`, compose `graphdb` service, and tiered
  tests (disabled, unreachable, recording-fake with Cypher assertions).
- The **opt-in live test** (`NOESIS_GRAPHDB_LIVE_TEST_URL`, e.g.
  `localhost:6379` against `docker run falkordb/falkordb`) skips unless a real
  server is reachable.
- **Live verification performed** against `falkordb/falkordb:latest`:
  9/9 context-graph tests including the real roundtrip (writes, keyword
  retrieval, live tenant isolation), plus a full demo run — plan node
  retrieved prior context (3 nodes), memory node committed 25/25 graph
  writes, the REST endpoint returned the subgraph, and a mid-run engine
  outage was survived with honest "graph unavailable" evidence while the
  research run completed.
- Graph failure never blocks a research run; relational memory is primary.
- Graph state IS durably persisted: the compose `graphdb` service and the
  documented dev container both run with AOF (`--appendonly yes`,
  `everysec`) plus RDB snapshots on a named volume mounted at the image's
  real data dir (`/var/lib/falkordb/data` — the image's own `--dir` flag
  overrides `REDIS_ARGS`). Verified: graph nodes survived `docker restart`,
  full `docker rm -f` + fresh container, and a Docker engine crash.
- Docker Desktop on this host crashed repeatedly during testing (host
  instability, not stack-related); the persistence layer now rides it out.

## Not implemented / deferred

- External imagery: the Celestial Gallery needs network access to NASA
  (`api.nasa.gov` APOD primary, `images-api.nasa.gov` fallback, 6 h disk
  cache, DEMO_KEY rate limits). Observed 2026-10: APOD returns generic
  NASA-logo placeholder entries for every date, so the connector detects
  them and transparently switches to NASA's Image & Video Library — the
  response `source`/`note` always states which provider served the images;
  placeholders are never presented as photographs.
- Isochrones in the Stellar Lab are derived from the bundled EEP-matched
  tracks (fixed-age interpolation per grid mass), not from official PARSEC
  isochrone tables; masses whose tracks do not span the requested age are
  omitted and reported (`excluded_masses_msun`, shown in the UI tooltip and
  footnote). The track-browser PNG export renders tracks + reference stars
  only — isochrone overlays exist in the interactive view.
- Real telescope/archive OAuth flows: archive queries use documented
  unauthenticated public APIs only.
- No hard multi-tenancy beyond app-layer filters on SQLite; production
  PostgreSQL RLS policies exist in migrations but are not exercised by CI.
- ~~Docker images untested~~ **Verified end-to-end**: `docker compose build`
  and `up` succeed; Postgres migrations applied on the real database
  (16 tables + 14 RLS policies), backend healthy, nginx SPA + `/api` proxy
  chain works (register → login → authenticated calls), and the FalkorDB
  context layer connects over the compose network. Host ports are
  parameterized (`NOESIS_BACKEND_PORT`, `NOESIS_FRONTEND_PORT`,
  `NOESIS_GRAPHDB_UI_PORT`) so the stack can run alongside dev servers.
  All Python dependencies ship manylinux wheels, so the backend image needs
  no compiler toolchain (apt removed — it is unavailable in some build
  sandboxes).
- Horizontal worker scaling: worker count is per-process threads, not
  distributed across machines.