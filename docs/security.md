# NOESIS AI — Security Notes

## Authentication & authorization

- JWT (HS256) issued by `/api/auth/login`; `NOESIS_JWT_SECRET` must be changed
  in production (`.env.example` ships an obviously-insecure dev default).
- Tokens carry `tenant_id` and `user_id`. Every repository/query layers a
  `tenant_id` filter; artifact paths are prefixed with the tenant directory.

## Tenant isolation

- Episodic/semantic/procedural memory queries are scoped to the caller's
  tenant; cross-tenant reads return 404/403.
- Artifact download re-resolves the artifact row under the caller's tenant
  even if a path is guessed — path traversal beyond the tenant root is
  rejected by construction (UUID-named files under `artifacts/<tenant>/...`).

## Input handling

- Pydantic models validate all request bodies; scientific parameters are
  range-checked (eccentricity, masses, redshifts) with 422 responses.
- Uploaded FITS files are size-limited and parsed with Astropy; FITS parsing
  is done in a subprocess with a wall-clock deadline for simulations as well.
- Outbound archive queries are rate-limited per user
  (`NOESIS_RATE_LIMIT_PER_MINUTE`) and target only allow-listed public API
  endpoints.

## Secrets & configuration

- No secret is hardcoded outside the documented dev default for
  `NOESIS_JWT_SECRET`. Production deployments must set it via environment.
- LLM API keys (`NOESIS_LLM_API_KEY`) are read only from the environment and
  never logged or echoed into artifacts.
- CORS is restricted to configured origins (`NOESIS_CORS_ORIGINS`).

## Known gaps (honest status)

- No refresh tokens; JWT lifetime controls session length.
- Local embedding mode means semantic search is not an embedding of an
  external model unless `NOESIS_EMBEDDING_PROVIDER=openai` is configured.
- SQLite dev mode does not enforce row-level security; the PostgreSQL
  migration includes RLS policies (`20261017_rls_policies`) used in
  production.