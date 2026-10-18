# NOESIS AI

Autonomous multi-agent astrophysics & cosmology research platform: durable
scientific memory, agent collaboration with evidence, real astrophysics
computation (REBOUND, Astropy, SciPy, emcee), and interactive visualization.

## What it does

- **Eleven specialized agents** (orchestrator, knowledge, math, stellar,
  celestial, cosmology, observation, simulation, validation, memory
  coordinator, report) execute a resumable research graph over a durable
  job queue with retries and timeouts.
- **Three memory systems** — episodic experiments, versioned semantic
  knowledge with provenance, and procedural workflows that require executed
  evidence before they become approved and reusable.
- **FalkorDB context layer** — the graph is the platform's shared map of prior research. Agents query it before and during a run to retrieve relevant linked work; the memory coordinator writes the completed run back, so later runs can discover its evidence. Every node and query is tenant-scoped.

  ```mermaid
  flowchart LR
      subgraph Run["Research run"]
          Prompt["Research question"] --> Orchestrator["Orchestrator<br/>question + domain rules choose plan"]
          Orchestrator -->|"tenant + keywords"| Graph
          Graph -->|"matches + edges + one-hop neighbors"| Context["Retrieved context<br/>nodes + relationships"]
          Context -->|"prior-work context"| Orchestrator
          Context -->|"linked evidence"| Knowledge["Knowledge agent"]
          Orchestrator --> Agents["Configured domain agents"]
          Knowledge --> Agents
          Agents --> Validation["Validation"]
          Validation --> Memory["Memory coordinator"]
          Memory -->|"persist completed run"| Graph
      end

      subgraph Graph["FalkorDB · tenant-scoped context graph"]
          Session["Session"] -->|RECORDED| Episode["Episode"]
          Episode -->|TESTS| Question["Question"]
          Episode -->|APPROVES / PENDING| Procedure["Procedure"]
          Episode -->|PRODUCES| Experiment["Experiment"]
          Experiment -->|VALIDATED_BY| Check["Validation"]
          KnowledgeNode["Knowledge"] -->|SUPPORTED_BY| Experiment
          Artifact["Artifact"]
      end
  ```

  **Where graph context enters the work:**
  - The orchestrator searches by words from the research question; FalkorDB returns matching nodes, their relationships, and one-hop neighbors. Those results are attached to the plan output and evidence.
  - The knowledge agent repeats the keyword lookup and receives the expanded subgraph alongside semantic-memory and literature results. These linked procedures, experiments, and validations provide prior-work context for the agents.
  - After validation, the memory coordinator upserts the question, session, episode, procedure, experiment, validation, knowledge, and artifact nodes and their supported relationships. Artifact nodes are recorded without a relationship edge in the current writer.
  - **Decision boundary:** domain selection and plan shape currently come from the research question and configured domain plans; run resumption comes from the saved checkpoint. FalkorDB supplies linked context to the agents, but does not currently choose plan steps, skip work, or resume a run.
  - The context endpoint is `GET /api/memory/context`. Queries are tenant-scoped and parameterized. If FalkorDB is disabled or unavailable, evidence reports that state rather than presenting an unavailable graph as an empty result.

- **Real computation** — REBOUND N-body sweeps with conservation validation,
  ΛCDM distance ladder + MCMC posterior estimation, HR-diagram stellar
  modeling, FITS/catalog/light-curve tools over public archive APIs.
- **Evidence-driven UI** — live SSE agent timeline, coordination graph,
  memory explorer, trajectory and posterior plots, downloadable reproducible
  reports.

## Quickstart

```bash
# Backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
alembic upgrade head
NOESIS_WORKERS_ENABLED=true uvicorn app.main:app --port 8000

# Frontend (second shell)
cd frontend && npm install && npm run dev    # http://localhost:5173
```

Run the full 12-step end-to-end demo against a running backend:

```bash
python scripts/e2e_demo.py --base http://127.0.0.1:8000
```

## Tests

```bash
cd backend && pytest tests/ -q           # 37 tests
cd frontend && npm run build             # type-check + production build
```

## Repository layout

```text
.
├── backend/                 FastAPI app, orchestration, memory, physics, tests
│   ├── app/
│   │   ├── api/             Routes: auth, research, memory, simulation, agents
│   │   ├── orchestration/   Graph, state, handlers, workers
│   │   ├── physics/         Celestial, stellar, cosmology, observations
│   │   ├── memory/          Episodic, semantic, procedural, FalkorDB context
│   │   └── validation/      Scientific validation checks
│   └── migrations/          Alembic revisions (including PostgreSQL RLS)
├── frontend/                React + Vite + TypeScript + Tailwind (9 pages)
├── scripts/                 e2e_demo.py reproducible experiment
├── docs/                    Architecture, API, security, deployment, limitations
└── artifacts/               Tenant-scoped plots, trajectories, and reports
```

## Documentation

- [Architecture](docs/architecture.md)
- [API reference](docs/api.md)
- [Deployment](docs/deployment.md)
- [Security](docs/security.md)
- [Limitations — actual status](docs/limitations.md)
- [.env.example](.env.example) · [docker-compose.yml](docker-compose.yml)

## First experiment (included)

"How does changing the mass and orbital configuration of a third body affect
the stability of an initially stable two-body system?" — run
`scripts/e2e_demo.py`: plan → equations → simulation setup → 5-point mass
sweep (real REBOUND integrations) → validation → memory → report. The demo
finishes re-using the saved procedure and emitting `demo_report.md` with
per-run stability metrics and energy-drift numbers.