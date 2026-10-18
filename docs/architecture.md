# NOESIS AI — Architecture

## Overview

NOESIS AI is a multi-agent astrophysics and cosmology research platform. A
FastAPI backend hosts a durable job queue, three persistent memory systems,
scientific computation engines, and an eleven-agent orchestration graph; a
React/Vite/TypeScript frontend renders the research workspace.

```
┌────────────────────────── frontend (React + Vite + Tailwind) ──────────────────────────┐
│ Login · Dashboard · Workspace (chat + live SSE run) · Coordination (React Flow)        │
│ Memory Explorer · Celestial Sim · Stellar Lab · Cosmology Lab · Observation ·          │
│ Celestial Gallery (NASA imagery + lightbox) · Reports                                  │
└───────────────────────────────────────┬────────────────────────────────────────────────┘
                                        │ REST + SSE (JWT)
┌───────────────────────────────────────▼────────────────────────────────────────────────┐
│ FastAPI (app/api/*)                                                                    │
│  auth · research · memory · simulation · agent routes                                 │
├───────────────────────────────┬───────────────────────────────────────────────────────┤
│ Orchestration (LangGraph-     │ Scientific engines                                    │
│ style durable graph)          │  physics/celestial   REBOUND N-body                   │
│  11 agents, typed state,      │  physics/stellar     PARSEC tracks + analytic MS model │
│  dependency-ordered nodes,    │  physics/cosmology   ΛCDM, Friedmann, emcee MCMC       │
│  resumable execution          │  physics/observations FITS, catalogs, light curves    │
├───────────────────────────────┼───────────────────────────────────────────────────────┤
│ Durable job queue + workers   │ Validation (conservation, Kepler, cross-checks)       │
│  retries, timeouts, heartbeat │ Artifacts (plots, trajectories, reports — tenant-path)│
├───────────────────────────────┴───────────────────────────────────────────────────────┤
│ Memory: episodic · semantic (pgvector/local embeddings + versioning) · procedural     │
│ Context layer: FalkorDB openCypher graph (tenant-scoped links across memory)           │
│ Storage: SQLite (dev) / PostgreSQL+pgvector (prod) · Redis (optional) · file artifacts │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

## Key design decisions

- **Evidence over assertion.** Agents record which tool actually ran and what
  it returned; validation decisions persist next to the results they judged.
- **Durable execution.** Every run is a job row with attempts, heartbeat, and
  timeout; workers use per-thread DB sessions so parallel nodes do not share
  connections. A restart resumes incomplete jobs.
- **Scientific separation.** Numerical engines return structured dicts
  (snapshots, diagnostics, analytics); LLM text (when an LLM is configured)
  only ever explains engine output and never replaces it.
- **Memory versioning.** Semantic and procedural records are version chains
  (`parent_id`); listings and vector search return only the latest version of
  each chain. Procedures start `pending` and require execution evidence to be
  `approved`.
- **Tenant isolation.** JWT carries `tenant_id`; every query and artifact path
  is tenant-scoped.
- **Runtime theming without state loss.** The Tailwind palette is emitted as
  CSS channel variables (light on `:root`, dark on `html.dark`), so toggling
  one class repaints every utility. Charts need literal hex colors, so they
  subscribe to the toggle via `useTheme()` (`useSyncExternalStore`) and
  re-render in place — the route outlet is keyed by path only, so pages like
  the Stellar Lab keep their inputs, loaded tracks and open views across a
  theme switch. Overlay surfaces that must stay dark in both themes (the
  Celestial Gallery lightbox) localize the dark variables with a
  `.dark-scope` class.
- **Context layer (FalkorDB).** A property graph links
  Question→Session→Episode→Procedure/Experiment/Knowledge/Validation/Artifact
  with `RECORDED`, `TESTS`, `APPROVES`, `PRODUCES`, `VALIDATED_BY`, and
  `SUPPORTED_BY` edges. The orchestrator's plan node traverses it before a
  run; the memory coordinator writes it after a run, gated on relational
  memory succeeding. Every statement filters `tenant_id = $tenantId`, uses
  parameterized Cypher, and MERGEs endpoints before relationships. If
  `NOESIS_GRAPHDB_URL` is empty or the server is unreachable, every operation
  degrades to a no-op with `available:false` + reason — evidence text states
  "context graph unavailable", never a fabricated retrieval.

## Execution flow (research run)

1. `POST /api/sessions/{id}/run` enqueues a job.
2. Graph nodes execute in dependency order; each publishes `node_started` /
   `node_succeeded` / `node_failed` SSE events to `/jobs/{id}/events`.
3. Handlers write intermediate results into typed shared state guarded by
   `state_version`.
4. Validation node runs unit/provenance/conservation checks and persists them.
5. Memory coordinator writes episodic records and approved procedures.
6. Report node renders a reproducible markdown report linking artifacts.