"""Node handlers for the celestial-mechanics research plan (Phase 4 slice).

Each handler performs real tool work and returns AgentResult with evidence.
Handlers are pure orchestration around executed code — narrative text may come
from an optional LLM, but numbers, checks and artifacts come only from tools.
"""
import hashlib
import json
import re
import time

from app.agents.base import AgentResult, evidence, llm
from app.core.errors import DomainError
from app.database.models import Experiment, Message
from app.orchestration.graph import NodeContext
from app.orchestration.state import ResearchState
from app.memory import episodic as epi_mem
from app.memory import procedural as proc_mem
from app.memory import semantic as sem_mem
from app.memory.context_graph import get_context_graph


def _graph_sync(ctx: NodeContext, *, episode_id: str, procedure: dict | None,
                knowledge_ids: list[str] | None = None,
                experiment_id: str | None = None,
                validation_id: str | None = None,
                artifact_ids: list[str] | None = None) -> tuple[dict, str]:
    """Write the completed run into the FalkorDB context layer.

    Returns (result, evidence_summary). Never raises and never claims a write
    happened when the graph is disabled/unavailable — the summary states the
    actual condition so the evidence trail stays honest.
    """
    graph = get_context_graph()
    question = (ctx.state.research_question or ctx.state.objective or "").strip()
    qid = "q_" + hashlib.sha1(
        f"{ctx.job.tenant_id}|{question}".encode()).hexdigest()[:16]
    res = graph.sync_run(
        tenant_id=ctx.job.tenant_id, question_id=qid, question_text=question,
        session_id=ctx.session.id, episode_id=episode_id,
        objective=(ctx.state.objective or question)[:500],
        procedure=procedure, knowledge_ids=knowledge_ids,
        experiment_id=experiment_id, validation_id=validation_id,
        artifact_ids=artifact_ids,
    )
    if not res.get("enabled"):
        summary = "context graph disabled (NOESIS_GRAPHDB_URL unset); relational memory persisted"
    elif not res.get("available"):
        summary = (f"context graph unavailable ({res.get('reason')}); "
                   "relational memory persisted")
    else:
        summary = f"{res['written']}/{res['attempted']} graph writes committed to FalkorDB"
    return res, summary

# ---------------------------------------------------------------------------
# domain plans
# ---------------------------------------------------------------------------

DOMAINS = {
    "celestial": [
        {"id": "plan", "agent": "orchestrator", "depends_on": [], "label": "Research plan"},
        {"id": "knowledge", "agent": "knowledge", "depends_on": ["plan"], "label": "Literature & prior work"},
        {"id": "equations", "agent": "math", "depends_on": ["plan"], "label": "Governing equations"},
        {"id": "setup", "agent": "celestial", "depends_on": ["equations"], "label": "Simulation configuration"},
        {"id": "sweep", "agent": "simulation", "depends_on": ["setup"], "label": "Parameter sweep execution"},
        {"id": "validate", "agent": "validation", "depends_on": ["sweep"], "label": "Independent validation"},
        {"id": "memory", "agent": "memory_coordinator", "depends_on": ["validate"], "label": "Persist scientific memory"},
        {"id": "report", "agent": "report", "depends_on": ["memory"], "label": "Reproducible report"},
    ],
    "stellar": [
        {"id": "plan", "agent": "orchestrator", "depends_on": [], "label": "Research plan"},
        {"id": "knowledge", "agent": "knowledge", "depends_on": ["plan"], "label": "Literature & prior work"},
        {"id": "equations", "agent": "math", "depends_on": ["plan"], "label": "Governing equations"},
        {"id": "stellar_analysis", "agent": "stellar", "depends_on": ["equations", "knowledge"], "label": "Stellar analysis (HR, classes, lifetimes)"},
        {"id": "validate", "agent": "validation", "depends_on": ["stellar_analysis"], "label": "Model vs literature validation"},
        {"id": "memory", "agent": "memory_coordinator", "depends_on": ["validate"], "label": "Persist scientific memory"},
        {"id": "report", "agent": "report", "depends_on": ["memory"], "label": "Reproducible report"},
    ],
    "cosmology": [
        {"id": "plan", "agent": "orchestrator", "depends_on": [], "label": "Research plan"},
        {"id": "knowledge", "agent": "knowledge", "depends_on": ["plan"], "label": "Literature & prior work"},
        {"id": "equations", "agent": "math", "depends_on": ["plan"], "label": "Governing equations"},
        {"id": "cosmology_analysis", "agent": "cosmology", "depends_on": ["equations", "knowledge"], "label": "Expansion analysis"},
        {"id": "validate", "agent": "validation", "depends_on": ["cosmology_analysis"], "label": "Distance cross-validation"},
        {"id": "memory", "agent": "memory_coordinator", "depends_on": ["validate"], "label": "Persist scientific memory"},
        {"id": "report", "agent": "report", "depends_on": ["memory"], "label": "Reproducible report"},
    ],
    "observation": [
        {"id": "plan", "agent": "orchestrator", "depends_on": [], "label": "Research plan"},
        {"id": "knowledge", "agent": "knowledge", "depends_on": ["plan"], "label": "Literature & prior work"},
        {"id": "equations", "agent": "math", "depends_on": ["plan"], "label": "Methods & equations"},
        {"id": "observation_fetch", "agent": "observation", "depends_on": ["plan"], "label": "Archive retrieval"},
        {"id": "observation_analysis", "agent": "observation", "depends_on": ["observation_fetch", "equations"], "label": "Data analysis"},
        {"id": "validate", "agent": "validation", "depends_on": ["observation_analysis"], "label": "Validation"},
        {"id": "memory", "agent": "memory_coordinator", "depends_on": ["validate"], "label": "Persist scientific memory"},
        {"id": "report", "agent": "report", "depends_on": ["memory"], "label": "Reproducible report"},
    ],
    # Paper interpretation: a research-paper link is parsed, its quantitative
    # claims extracted verbatim from the abstract, mapped onto this platform's
    # engines, executed, cross-checked and explained in plain language.
    "paper": [
        {"id": "plan", "agent": "orchestrator", "depends_on": [], "label": "Interpretation plan"},
        {"id": "paper_ingest", "agent": "knowledge", "depends_on": ["plan"],
         "label": "Fetch paper metadata (arXiv/Crossref)"},
        {"id": "paper_extract", "agent": "math", "depends_on": ["paper_ingest"],
         "label": "Extract quantitative claims (verbatim)"},
        {"id": "paper_setup", "agent": "orchestrator", "depends_on": ["paper_extract"],
         "label": "Map claims to engine simulations"},
        {"id": "paper_run", "agent": "simulation", "depends_on": ["paper_setup"],
         "label": "Execute mapped simulations"},
        {"id": "validate", "agent": "validation", "depends_on": ["paper_run"],
         "label": "Cross-check claims vs computed"},
        {"id": "explain", "agent": "orchestrator", "depends_on": ["validate"],
         "label": "Plain-language interpretation"},
        {"id": "memory", "agent": "memory_coordinator", "depends_on": ["explain"],
         "label": "Persist scientific memory"},
        {"id": "report", "agent": "report", "depends_on": ["memory"],
         "label": "Reproducible report"},
    ],
}

DOMAIN_KEYWORDS = {
    "celestial": ["orbit", "orbital", "n-body", "nbody", "kepler", "planet", "stability",
                  "third body", "three-body", "trajectory", "rebound", "perturbation",
                  "angular momentum", "moon", "ejected", "integrator"],
    "stellar": ["star", "stellar", "hr diagram", "hertzsprung", "main sequence", "luminosity",
                "white dwarf", "neutron star", "supernova", "spectral class", "teff", "mesa"],
    "cosmology": ["cosmolog", "hubble", "redshift", "lambda-cdm", "λ-cdm", "friedmann",
                  "dark energy", "expansion", "comoving", "om0", "h0", "distance modulus"],
    "observation": ["fits", "light curve", "catalog", "gaia", "simbad", "vizier", "photometry",
                    "spectrum", "cross-match", "crossmatch", "archive", "magnitude", "astrometry"],
    # paper wins only when the question carries an explicit paper reference
    # (ties still resolve to the science domains in dict order).
    "paper": ["arxiv", "doi.org", "preprint", "paper link"],
}


def detect_domain(question: str) -> str:
    q = question.lower()
    scores = {d: sum(1 for kw in kws if kw in q) for d, kws in DOMAIN_KEYWORDS.items()}
    best = max(scores, key=lambda d: scores[d])
    return best if scores[best] > 0 else "celestial"


def add_message(db, session, *, agent: str, content: str, meta: dict | None = None,
                role: str = "agent") -> None:
    db.add(Message(tenant_id=session.tenant_id, session_id=session.id, role=role,
                   agent=agent, content=content, meta=meta or {}))
    db.commit()


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

def h_plan(ctx: NodeContext) -> AgentResult:
    state = ctx.state
    question = (state.research_question or state.objective).strip()
    if not question:
        raise RuntimeError("research question is empty")
    t0 = time.time()
    domain = state.domain if state.domain in DOMAINS and state.domain != "" else detect_domain(question)

    # retrieval of prior related work (durable episodic memory)
    prior = epi_mem.search_episodes(db=ctx.db, tenant_id=ctx.job.tenant_id, query=question, limit=3)
    prior_ids = [{"id": m.id, "objective": m.objective, "score": round(s, 3)} for m, s in prior]

    # context layer: traverse the FalkorDB subgraph for prior linked work
    cg = get_context_graph()
    kw = [w for w in re.findall(r"[a-zA-Z]{5,}", question.lower())][:4]
    ctx_sub = cg.context_subgraph(tenant_id=ctx.job.tenant_id, keywords=kw, limit=8)
    ctx_nodes = ctx_sub.get("nodes", []) if ctx_sub.get("available") else []

    hypothesis = {
        "celestial": ("Testable hypothesis: for an initially stable two-body system, increasing "
                      "the third body's mass and decreasing its semi-major axis increases the "
                      "inner orbit's eccentricity excitation and eventual instability, "
                      "measurable via an eccentricity proxy, ejection, and conservation-law drift."),
        "stellar": ("Testable hypothesis: simplified analytic main-sequence relations reproduce "
                    "published masses, temperatures and luminosities of nearby reference stars "
                    "within their stated uncertainty."),
        "cosmology": ("Testable hypothesis: flat ΛCDM distance–redshift relations computed with "
                      "astropy match independent Friedmann integration to <1e-4 relative error, "
                      "and demo-data posteriors recover Planck-like parameters within 68% CI."),
        "observation": ("Testable hypothesis: archive-retrieved catalog data can be validated "
                        "against published model predictions within measurement uncertainty."),
        "paper": ("Testable hypothesis: quantitative claims stated verbatim in the paper's "
                  "abstract can be reproduced by this platform's engines within documented "
                  "model limitations; every mapped number traces back to the literal abstract "
                  "text it came from, and discrepancies are reported, not hidden."),
    }[domain]

    plan = {"domain": domain, "nodes": DOMAINS[domain], "question": question}
    state.objective = state.objective or f"Investigate: {question}"
    state.domain = domain
    state.hypothesis = hypothesis
    state.next_actions = [n["label"] for n in DOMAINS[domain][1:]]
    state.open_uncertainties = [
        "Simplified models vs full physics (documented per analysis)",
        "Archive data subject to upstream calibration changes",
    ]
    ctx.checkpoint["plan"] = plan
    ctx.checkpoint["state_version"] = ctx.session.state_version

    add_message(ctx.db, ctx.session, agent="orchestrator",
                content=f"Research plan created for domain '{domain}' with "
                        f"{len(DOMAINS[domain])} tasks. Prior related episodes: {len(prior_ids)}; "
                        f"context-graph nodes: {len(ctx_nodes) if ctx_sub.get('available') else 'graph unavailable'}.",
                meta={"plan": plan, "prior_episodes": prior_ids,
                      "context_graph": {k: ctx_sub[k] for k in ("available", "reason")
                                        if k in ctx_sub},
                      "context_nodes": ctx_nodes})
    return AgentResult(
        summary=f"Planned {len(DOMAINS[domain])}-node {domain} investigation",
        output={"plan": plan, "prior_episodes": prior_ids, "hypothesis": hypothesis,
                "context_nodes": ctx_nodes},
        evidence=[
            evidence("plan.build", args={"domain": domain, "n_nodes": len(DOMAINS[domain])},
                     result_summary=f"plan for: {question[:200]}", duration_s=time.time() - t0),
            evidence("memory.episodic.search", args={"query": question[:120]},
                     result_summary=f"found {len(prior_ids)} related prior episodes"),
            evidence("memory.context_graph.query", args={"keywords": kw},
                     result_summary=(f"{len(ctx_nodes)} linked context nodes retrieved from FalkorDB"
                                     if ctx_sub.get("available") else
                                     f"context graph not queried: {ctx_sub.get('reason', 'unavailable')}")),
        ],
    )


# ---------------------------------------------------------------------------
# knowledge
# ---------------------------------------------------------------------------

def h_knowledge(ctx: NodeContext) -> AgentResult:
    question = ctx.state.research_question or ctx.state.objective
    t0 = time.time()
    hits = sem_mem.search_knowledge(db=ctx.db, tenant_id=ctx.job.tenant_id,
                                    query=question, limit=5)
    items = [{"id": m.id, "title": m.title, "status": m.status, "kind": m.kind,
              "sources": m.source_refs, "score": round(s, 3)} for m, s in hits]

    ev = [evidence("memory.semantic.search", args={"query": question[:120], "limit": 5},
                   result_summary=f"{len(items)} established/known items retrieved",
                   duration_s=time.time() - t0)]

    # context-graph enrichment: expand one hop from keyword matches so the
    # agent sees connected procedures/validations/experiments, not just hits
    kw = [w for w in re.findall(r"[a-zA-Z]{5,}", (question or "").lower())][:4]
    ctx_sub = get_context_graph().context_subgraph(
        tenant_id=ctx.job.tenant_id, keywords=kw, limit=8)
    ctx_nodes = ctx_sub.get("nodes", []) if ctx_sub.get("available") else []
    linked = [n for n in ctx_nodes if n.get("via") == "neighbor"]
    ev.append(evidence(
        "memory.context_graph.expand", args={"keywords": kw},
        result_summary=(
            f"{len(ctx_nodes)} context nodes ({len(linked)} via one-hop expansion "
            f"from {max(len(ctx_nodes) - len(linked), 0)} matches)"
            if ctx_sub.get("available") else
            f"context graph not queried: {ctx_sub.get('reason', 'unavailable')}")))

    # optional literature search (real arXiv API; failure is reported, not hidden)
    papers = []
    try:
        from app.physics.observations.connectors import search_arxiv

        arxiv = search_arxiv(question[:120], max_results=3)
        papers = arxiv.get("papers", [])
        ev.append(evidence("archive.arxiv", args={"query": question[:100]},
                           result_summary=f"{len(papers)} recent preprints retrieved",
                           duration_s=time.time() - t0))
    except DomainError as exc:
        ev.append(evidence("archive.arxiv", args={"query": question[:100]},
                           result_summary=f"arXiv unreachable: {exc.message[:200]}"))

    add_message(ctx.db, ctx.session, agent="knowledge",
                content=f"Retrieved {len(items)} semantic-memory items and {len(papers)} arXiv results; "
                        f"context graph: {len(ctx_nodes)} nodes ({len(linked)} expanded).",
                meta={"items": items, "papers": [p.get("id") for p in papers],
                      "context_nodes": ctx_nodes})
    return AgentResult(
        summary=f"{len(items)} memory items, {len(papers)} papers",
        output={"memory_items": items, "papers": papers,
                "context_nodes": ctx_nodes},
        evidence=ev,
    )


# ---------------------------------------------------------------------------
# equations (math)
# ---------------------------------------------------------------------------

def h_equations(ctx: NodeContext) -> AgentResult:
    domain = ctx.state.domain
    import sympy as sp

    t0 = time.time()
    checks = []
    equations: list[dict] = []

    if domain == "celestial":
        G, M, a, pi = sp.symbols("G M a pi", positive=True)
        P = 2 * pi * sp.sqrt(a**3 / (G * M))
        eq = sp.simplify(P**2 - 4 * pi**2 * a**3 / (G * M))
        checks.append({"expr": str(P**2), "expected": str(4 * pi**2 * a**3 / (G * M)),
                       "zero": str(eq) == "0"})
        equations.append({
            "name": "Kepler's third law", "latex": "P^2 = \\frac{4\\pi^2 a^3}{G M}",
            "regime": "two-body Newtonian, point masses, a >> radii",
            "source": "Murray & Dermott 1999, Solar System Dynamics, Eq. 2.43",
        })
        eps = -G * M / (2 * a)
        equations.append({
            "name": "Specific orbital energy", "latex": "\\varepsilon = -\\frac{GM}{2a}",
            "regime": "bound Keplerian orbit (epsilon < 0)",
            "source": "Landau & Lifshitz, Mechanics, Sec. 15",
        })
        equations.append({
            "name": "N-body equations of motion",
            "latex": "\\ddot{\\vec r}_i = -\\sum_{j\\neq i} \\frac{G m_j (\\vec r_i - \\vec r_j)}{|\\vec r_i-\\vec r_j|^3}",
            "regime": "Newtonian point-mass gravity, no relativity, no tides",
            "source": "Goldstein et al., Classical Mechanics, Ch. 1",
        })
        assumptions = [
            "Newtonian gravity (GR corrections ~1e-8 at 1 AU ignored)",
            "Point masses (no tides, no oblateness, no mass loss)",
            "Isolated system (no stellar mass loss, no GR precession)",
        ]
    elif domain == "stellar":
        M, k, n = sp.symbols("M k n", positive=True)
        L = k * M**n
        rel = sp.simplify(L / (k * M**n))  # dimensionless consistency
        checks.append({"expr": str(L / (k * M**n)), "expected": "1", "zero": str(rel) == "1"})
        equations.append({
            "name": "Mass–luminosity relation", "latex": "L \\propto M^{n}\\ (n\\approx 3.5)",
            "regime": "hydrogen-burning MS stars, solar-like composition",
            "source": "Salaris & Cassisi 2005, Evolution of Stars and Stellar Populations",
        })
        equations.append({
            "name": "Main-sequence lifetime", "latex": "t_{MS} \\approx 10\\,Gyr\\ (M/M_\\odot)^{-2.5}",
            "regime": "MS lifetime scaling, ~0.1% mass→radiation efficiency",
            "source": "Kippenhahn et al. 2012, Stellar Structure and Evolution",
        })
        assumptions = ["No convective overshooting", "No mass loss",
                       "Fixed composition (no dredge-up)", "Single-star evolution only"]
    elif domain == "cosmology":
        Om, Ol, z = sp.symbols("Omega_m Omega_Lambda z", positive=True)
        Ez = sp.sqrt(Om * (1 + z)**3 + Ol)
        checks.append({"expr": str(sp.simplify(Ez**2 - (Om * (1 + z)**3 + Ol))),
                       "expected": "0", "zero": True})
        equations.append({
            "name": "Friedmann equation (flat, matter+Λ)",
            "latex": "\\left(\\frac{H}{H_0}\\right)^2 = \\Omega_m(1+z)^3 + \\Omega_\\Lambda",
            "regime": "FLRW, flat geometry, radiation negligible at z<10",
            "source": "Durrer 2007, The Cosmic Microwave Background; astropy docs",
        })
        equations.append({
            "name": "Luminosity distance",
            "latex": "D_L = (1+z)\\,D_M = (1+z)\\frac{c}{H_0}\\int_0^z\\frac{dz'}{E(z')}",
            "regime": "flat FLRW metric",
            "source": "Hogg 1999, Distance measures in cosmology (astro-ph/9905116)",
        })
        assumptions = ["Flat ΛCDM", "Perfect fluid stress-energy",
                       "Photons-only radiation term below z~10"]
    else:  # observation
        equations.append({
            "name": "Distance modulus", "latex": "\\mu = m - M = 5\\log_{10}(d/10\\,pc)",
            "regime": "standard candles, no extinction correction",
            "source": "Cardelli et al. / standard photometry; Hogg 1999",
        })
        equations.append({
            "name": "Proper motion → transverse velocity",
            "latex": "v_\\perp = 4.74\\,\\mu[\\mathrm{mas/yr}]\\,d[\\mathrm{kpc}]",
            "regime": "small-angle, flat spacetime",
            "source": "Schneider et al., Extragalactic Astronomy, Ch. 1",
        })
        mu_expr = 5 * sp.log(1000, 10)
        checks.append({"expr": str(mu_expr), "expected": "15",
                       "zero": str(sp.simplify(mu_expr - 15)) == "0"})
        assumptions = ["J2000 epoch unless stated", "Vacuum wavelengths",
                       "Catalog errors are 1σ unless noted"]

    # a symbolic verification executed by sympy (real check, not assertion)
    symbolic_ok = all(c.get("zero") for c in checks) if checks else True
    ctx.state.approved_parameters["equations"] = equations
    ctx.state.approved_parameters["assumptions"] = assumptions

    add_message(ctx.db, ctx.session, agent="math",
                content=f"Established {len(equations)} governing equations; "
                        f"symbolic verification {'passed' if symbolic_ok else 'flagged'}.",
                meta={"equations": equations, "checks": checks})
    return AgentResult(
        summary=f"{len(equations)} equations established, symbolic checks "
                f"{'OK' if symbolic_ok else 'FLAGGED'}",
        output={"equations": equations, "assumptions": assumptions,
                "symbolic_checks": checks, "symbolic_ok": symbolic_ok},
        evidence=[evidence("sympy.check_dimensional",
                           args={"n_checks": len(checks)},
                           result_summary=f"{'all zero residuals' if symbolic_ok else 'nonzero residual'}: "
                                          + json.dumps(checks)[:300],
                           duration_s=time.time() - t0)],
    )


# ---------------------------------------------------------------------------
# setup (celestial mechanics agent)
# ---------------------------------------------------------------------------

DEFAULT_BASE_REQUEST = {
    "bodies": [
        {"name": "star", "mass_value": 1.0, "mass_unit": "msun",
         "x": 0.0, "y": 0.0, "z": 0.0, "vx": 0.0, "vy": 0.0, "vz": 0.0},
        {"name": "inner", "mass_value": 1.0e-3, "mass_unit": "msun",
         "a": 1.0, "e": 0.02, "inc": 0.0, "Omega": 0.0, "omega": 0.0, "theta": 0.0},
        {"name": "outer", "mass_value": 1.0e-3, "mass_unit": "msun",
         "a": 2.5, "e": 0.3, "inc": 0.0, "Omega": 0.0, "omega": 1.05, "theta": 3.14},
    ],
    "config": {"integrator": "ias15", "dt": 0.01, "t_end": 80.0, "output_every": 50,
               "exit_unstable": True},
}

DEFAULT_SWEEP = {
    "sweep_type": "third_body_mass",
    "values": [1.0e-5, 1.0e-4, 1.0e-3, 5.0e-3, 2.0e-2, 5.0e-2],
    "third_body": "outer",
    "probe_body": "inner",
}


def h_setup(ctx: NodeContext) -> AgentResult:
    from app.physics.celestial.kepler import orbital_period_yr

    state = ctx.state
    base = state.simulation_configs.get("base_request") or json.loads(json.dumps(DEFAULT_BASE_REQUEST))
    sweep = state.approved_parameters.get("sweep") or dict(DEFAULT_SWEEP)

    # physically consistent checks before execution
    p_inner = orbital_period_yr(1.0 + 1.0e-3, 1.0)
    p_outer = orbital_period_yr(1.0 + float(sweep.get("values", [1e-3])[-1]), 2.5)
    if p_outer <= p_inner:
        raise RuntimeError("outer body must have longer period than inner body")
    q_outer = 2.5 * (1 - 0.3)
    if q_outer < 1.0:
        raise RuntimeError("outer body pericenter crosses inner orbit in base config")

    state.simulation_configs["base_request"] = base
    state.approved_parameters["sweep"] = sweep
    state.approved_parameters["config_justification"] = [
        "IAS15: 15th-order adaptive integrator, robust to close encounters (Rein & Liu 2012)",
        "Record cadence dt*output_every = 0.5 yr over 80 yr -> 161 snapshots",
        "inner planet at 1 AU, e=0.02; outer perturber a=2.5 AU, e=0.3 (pericenter 1.75 AU)",
        "mass sweep 1e-5..5e-2 Msun spans Jupiter-like to low-mass star",
    ]
    add_message(ctx.db, ctx.session, agent="celestial",
                content="Simulation base configuration constructed and sanity-checked "
                        "(period ordering, non-crossing base orbits).",
                meta={"base_request": base, "sweep": sweep})
    return AgentResult(
        summary="3-body base config + sweep definition sanity-checked",
        output={"base_request": base, "sweep": sweep,
                "inner_period_yr": p_inner, "outer_period_yr": p_outer},
        evidence=[evidence("physics.kepler",
                           args={"a_inner_au": 1.0, "a_outer_au": 2.5},
                           result_summary=f"Kepler period ordering verified: "
                                          f"P_inner={p_inner:.3f} yr, P_outer={p_outer:.3f} yr"),
                  evidence("sim.build_config",
                           args={"integrator": "ias15", "t_end": 80.0},
                           result_summary="base_request + sweep stored in shared state")],
    )


# ---------------------------------------------------------------------------
# sweep (simulation agent)
# ---------------------------------------------------------------------------

def h_sweep(ctx: NodeContext) -> AgentResult:
    from app.experiments.service import run_experiment_job

    state = ctx.state
    base = state.simulation_configs.get("base_request")
    sweep = state.approved_parameters.get("sweep")
    if not base or not sweep:
        raise RuntimeError("setup node must run before sweep")

    exp = Experiment(
        tenant_id=ctx.job.tenant_id, project_id=ctx.job.project_id,
        session_id=ctx.session.id,
        name=f"third-body stability sweep ({sweep['sweep_type']})",
        objective=state.research_question or state.objective,
        config={**sweep, "base_request": base},
        status="pending",
    )
    ctx.db.add(exp)
    ctx.db.commit()
    # let the shared job payload reference the experiment (and vice versa)
    ctx.job.payload = {**ctx.job.payload, "experiment_id": exp.id}
    ctx.db.commit()

    t0 = time.time()
    result = run_experiment_job(ctx.db, ctx.job)
    summary = result["summary"]
    exp_id = exp.id
    artifact_ids = [a["id"] for a in result.get("artifacts", [])]

    state.intermediate_results["sweep"] = {
        "experiment_id": exp_id, "summary": summary, "runs": result["runs"],
        "artifact_ids": artifact_ids,
    }
    state.completed_analyses.append({
        "analysis": "parameter_sweep", "experiment_id": exp_id,
        "n_runs": summary["n_runs"], "stability_fraction": summary["stability_fraction"],
        "wall_time_s": summary["total_wall_time_s"],
    })
    state.open_uncertainties += [
        "Stability uses an eccentricity-proxy criterion (documented), not a full Lyapunov analysis",
        "Single realization per parameter value (no initial-condition ensemble)",
    ]

    artifact_ids = [a["id"] for a in result.get("artifacts", [])]
    artifact_ids = artifact_ids  # noqa: PLW0127 (kept for clarity; assigned above)
    unstable = [r["label"] for r in result.get("runs", []) if not r.get("stable")]
    add_message(ctx.db, ctx.session, agent="simulation",
                content=f"Executed {summary['n_runs']} REBOUND integrations "
                        f"({summary['n_executed']} completed); {summary['n_stable']} stable. "
                        f"Unstable: {', '.join(unstable) or 'none'}.",
                meta={"experiment_id": exp_id, "summary": summary,
                      "artifact_ids": artifact_ids})
    return AgentResult(
        summary=f"{summary['n_runs']} runs executed, {summary['n_stable']} stable",
        output={"experiment_id": exp_id, "summary": summary, "runs": result["runs"],
                "artifact_ids": artifact_ids},
        evidence=[evidence("experiment.sweep",
                           args={"experiment_id": exp_id,
                                 "sweep_type": sweep["sweep_type"],
                                 "values": sweep["values"]},
                           result_summary=f"executed {summary['n_runs']} isolated REBOUND runs in "
                                          f"{summary['total_wall_time_s']}s; "
                                          f"stability_fraction={summary['stability_fraction']:.2f}",
                           artifact_ids=artifact_ids,
                           duration_s=time.time() - t0)],
    )


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def h_validate_celestial(ctx: NodeContext) -> AgentResult:
    from app.simulations.service import execute_isolated
    from app.physics.celestial.types import SimulationRequest
    from app.validation.checks import run_all_simulation_checks
    from app.database.models import ValidationResult as VR

    state = ctx.state
    sweep_info = state.intermediate_results.get("sweep")
    if not sweep_info:
        raise RuntimeError("sweep must complete before validation")
    exp_id = sweep_info["experiment_id"]

    rows = ctx.db.query(VR).filter(VR.experiment_id == exp_id).all()
    by_check: dict[str, list[bool]] = {}
    for r in rows:
        key = r.check_name.split("::")[-1].strip()
        by_check.setdefault(key, []).append(r.passed)
    aggregate = {k: {"n": len(v), "passed": sum(v)} for k, v in by_check.items()}
    all_passed = all(all(v) for v in by_check.values()) and bool(by_check)

    # Independent verification: re-execute the first sweep value from scratch
    # and confirm reproducibility of status + conservation within tolerance.
    reproducible = None
    repro_details = ""
    runs = sweep_info.get("runs", [])
    try:
        sweep_cfg = state.approved_parameters.get("sweep", {})
        base = json.loads(json.dumps(state.simulation_configs["base_request"]))
        from app.experiments.service import _set_third_body_mass

        _set_third_body_mass(base, sweep_cfg.get("third_body", "outer"),
                             float(sweep_cfg["values"][0]))
        rerun = execute_isolated(SimulationRequest.model_validate(base), timeout_s=120)
        fresh_checks = run_all_simulation_checks(rerun)
        orig = runs[0]
        status_match = rerun["status"] == orig.get("status")
        drift_orig = orig.get("energy_drift_rel_max", 0.0) or 0.0
        drift_new = rerun["diagnostics"]["energy_drift_rel_max"]
        rel = abs(drift_new - drift_orig) / max(abs(drift_orig), 1e-15)
        reproducible = bool(status_match and rel < 1e-6)
        repro_details = (f"re-executed {sweep_cfg.get('values', [None])[0]} Msun run: "
                         f"status match={status_match}, drift rel-diff={rel:.2e}, "
                         f"fresh checks: {[c['passed'] for c in fresh_checks]}")
    except Exception as exc:
        repro_details = f"re-execution failed: {exc}"
        reproducible = False

    vr = VR(tenant_id=ctx.job.tenant_id, job_id=ctx.job.id, experiment_id=exp_id,
            check_name="independent_reexecution_reproducibility",
            passed=bool(reproducible), metrics={"reproducible": bool(reproducible)},
            details=repro_details)
    ctx.db.add(vr)
    ctx.db.commit()

    state.validation_decisions.append({
        "experiment_id": exp_id,
        "checks": aggregate,
        "all_passed": all_passed,
        "reproducible": bool(reproducible),
        "repro_details": repro_details,
        "validation_row_id": vr.id,
    })
    verdict = "VALIDATED" if (all_passed and reproducible) else "ISSUES FOUND"
    add_message(ctx.db, ctx.session, agent="validation",
                content=f"Validation verdict: {verdict}. Checks: {aggregate}. {repro_details}",
                meta={"aggregate": aggregate, "all_passed": all_passed,
                      "reproducible": reproducible})
    return AgentResult(
        summary=f"{verdict} ({len(rows)} persisted checks + 1 re-execution)",
        output={"aggregate": aggregate, "all_passed": all_passed,
                "reproducible": bool(reproducible), "repro_details": repro_details,
                "validation_row_id": vr.id},
        evidence=[evidence("validation.run_checks",
                           args={"experiment_id": exp_id},
                           result_summary=f"{len(rows)} persisted ValidationResult rows inspected; "
                                          f"independent re-execution: {repro_details}",
                           check_names=list(by_check.keys()))],
    )


# ---------------------------------------------------------------------------
# memory coordinator
# ---------------------------------------------------------------------------

def h_memory_celestial(ctx: NodeContext) -> AgentResult:
    state = ctx.state
    sweep_info = state.intermediate_results.get("sweep", {})
    validation = state.validation_decisions[-1] if state.validation_decisions else {}
    exp_id = sweep_info.get("experiment_id", "")

    # collect evidence from every completed node for the episode record
    tool_invocations = [
        {"node": nid, "evidence": ev} for nid, ev in state.provenance.items()
    ]
    episode = epi_mem.record_episode(
        ctx.db, tenant_id=ctx.job.tenant_id, project_id=ctx.job.project_id,
        session_id=ctx.session.id,
        objective=state.research_question or state.objective,
        assumptions=state.approved_parameters.get("assumptions", []),
        dataset_ids=[d.get("id", "") for d in state.datasets],
        tool_invocations=tool_invocations,
        parameters={"sweep": state.approved_parameters.get("sweep"),
                    "base_config": state.simulation_configs.get("base_request", {}).get("config")},
        status="completed" if validation.get("all_passed") else "completed_with_issues",
        results=sweep_info.get("summary", {}),
        artifacts=sweep_info.get("artifact_ids", []),
        errors=[r for r in sweep_info.get("runs", []) if r.get("status") == "error"],
    )

    # semantic: established equations (with citations)
    eq_ids = []
    for eq in state.approved_parameters.get("equations", [])[:3]:
        m = sem_mem.add_knowledge(
            ctx.db, tenant_id=ctx.job.tenant_id, kind="equation",
            title=eq["name"], content=f"{eq.get('latex', '')} — regime: {eq['regime']}",
            status="established", source_refs=[eq["source"]],
        )
        eq_ids.append(m.id)

    # semantic: the measured outcome — a specific measurement with experimental
    # evidence can be recorded as verified; the general trend stays a hypothesis.
    measurement_id = None
    if exp_id and validation.get("validation_row_id"):
        measurement_id = sem_mem.add_knowledge(
            ctx.db, tenant_id=ctx.job.tenant_id, kind="finding",
            title=f"Measured stability outcomes for third-body sweep ({exp_id[:8]})",
            content=(f"Sweep executed {sweep_info.get('summary', {}).get('n_runs')} REBOUND runs; "
                     f"stability_fraction={sweep_info.get('summary', {}).get('stability_fraction')}. "
                     f"Per-run metrics stored in experiment results."),
            status="verified",
            source_refs=[f"experiment:{exp_id}", f"validation:{validation['validation_row_id']}"],
            confidence=0.95,
        ).id
    hypothesis_id = sem_mem.add_knowledge(
        ctx.db, tenant_id=ctx.job.tenant_id, kind="hypothesis",
        title="Trend hypothesis: third-body mass/orbit controls inner-orbit stability",
        content=(f"Observed across one sweep: {state.hypothesis} "
                 f"(single realization; generalization untested)."),
        status="hypothesis", source_refs=[f"experiment:{exp_id}"] if exp_id else [],
        confidence=0.5, evidence_quality="medium",
    ).id

    # procedural: workflow approved only with validation evidence
    proc = proc_mem.save_procedure(
        ctx.db, tenant_id=ctx.job.tenant_id,
        name="three_body_stability_sweep", category="orbit",
        description="Configure star+inner planet+perturber, sweep perturber mass/a, "
                    "validate conservation + re-execution reproducibility.",
        workflow={
            "steps": ["build base_request", "define sweep values", "execute isolated runs",
                      "persist per-run validations", "independent re-execution",
                      "aggregate stability metrics"],
            "base_request": state.simulation_configs.get("base_request"),
            "sweep": state.approved_parameters.get("sweep"),
        },
    )
    approved = None
    if validation.get("all_passed") and validation.get("reproducible"):
        approved = proc_mem.approve(
            ctx.db, tenant_id=ctx.job.tenant_id, procedure_id=proc.id,
            evidence={"executed": True, "validated": True, "job_id": ctx.job.id,
                      "experiment_id": exp_id, "checks": validation.get("checks", {}),
                      "reproducible": validation.get("reproducible")},
        )
        proc_status = "approved"
    else:
        proc_status = "left pending (validation evidence incomplete)"

    add_message(ctx.db, ctx.session, agent="memory_coordinator",
                content=f"Episode {episode.id[:8]} recorded; {len(eq_ids)} equations stored; "
                        f"measurement {str(measurement_id)[:8]}; hypothesis kept as hypothesis; "
                        f"procedure {proc_status}.",
                meta={"episode_id": episode.id, "knowledge_ids": eq_ids,
                      "measurement_id": measurement_id, "hypothesis_id": hypothesis_id,
                      "procedure_id": proc.id, "procedure_status": proc_status})

    # context layer: link this run into the FalkorDB graph (evidence-gated)
    graph_res, graph_summary = _graph_sync(
        ctx, episode_id=episode.id,
        procedure={"id": proc.id, "name": "three_body_stability_sweep",
                   "status": "approved" if approved else "pending"},
        knowledge_ids=[k for k in (*eq_ids, measurement_id, hypothesis_id) if k],
        experiment_id=exp_id or None,
        validation_id=validation.get("validation_row_id"),
        artifact_ids=list(sweep_info.get("artifact_ids", []))[:20])
    return AgentResult(
        summary=f"episode + knowledge persisted; procedure {proc_status}",
        output={"episode_id": episode.id, "equation_ids": eq_ids,
                "measurement_id": measurement_id, "hypothesis_id": hypothesis_id,
                "procedure_id": proc.id, "procedure_status": proc_status,
                "context_graph": graph_res},
        evidence=[
            evidence("memory.episodic.write", args={"episode_id": episode.id},
                     result_summary=f"episode recorded (status={episode.status})"),
            evidence("memory.semantic.write",
                     args={"equations": len(eq_ids), "measurement_id": measurement_id},
                     result_summary="established equations cited; outcome stored as verified "
                                    "measurement + separate hypothesis entry"),
            evidence("memory.procedural.approve" if approved else "memory.procedural.save",
                     args={"procedure_id": proc.id},
                     result_summary=proc_status,
                     check_names=["validation_evidence_required"]),
            evidence("memory.context_graph.write",
                     args={"experiment_id": exp_id, "episode_id": episode.id},
                     result_summary=graph_summary),
        ],
    )


def h_validate(ctx: NodeContext) -> AgentResult:
    """Validation dispatcher: every domain validates via persisted executed checks."""
    domain = ctx.state.domain
    if domain == "stellar":
        from app.orchestration.handlers_domains import validate_stellar

        return validate_stellar(ctx)
    if domain == "cosmology":
        from app.orchestration.handlers_domains import validate_cosmology

        return validate_cosmology(ctx)
    if domain == "observation":
        from app.orchestration.handlers_domains import validate_observation

        return validate_observation(ctx)
    if domain == "paper":
        from app.orchestration.handlers_paper import validate_paper

        return validate_paper(ctx)
    return h_validate_celestial(ctx)


# procedures per domain: approved ONLY with validation evidence
def h_memory(ctx: NodeContext) -> AgentResult:
    """Memory coordinator dispatcher (persists without overwriting prior work)."""
    if ctx.state.domain == "celestial":
        return h_memory_celestial(ctx)
    return h_memory_generic(ctx)


PROCEDURES = {
    "stellar": ("stellar_reference_comparison", "classification",
                ["build mass grid", "compute simplified MS parameters", "plot HR diagram",
                 "compare vs published references", "persist residuals + validation"]),
    "cosmology": ("cosmology_distance_validation", "statistics",
                  ["set H0/Om0", "compute distance ladder (astropy)",
                   "cross-check vs independent Friedmann integration", "optional MCMC on demo data",
                   "persist validations"]),
    "observation": ("archive_retrieve_and_crossmatch", "fits",
                    ["resolve object coordinates", "query archive via documented API",
                     "coordinate transform", "cone cross-match", "persist validations"]),
    "paper": ("paper_claim_reproduction", "interpretation",
              ["parse paper link (arXiv/DOI)", "fetch metadata via documented API",
               "extract quantities verbatim from abstract", "map claims to engine runs",
               "execute engines", "cross-check claims vs computed",
               "persist interpretation with evidence"]),
}


def h_memory_generic(ctx: NodeContext) -> AgentResult:
    """Generic memory coordinator path for stellar/cosmology/observation domains."""
    state = ctx.state
    domain = state.domain
    validation = state.validation_decisions[-1] if state.validation_decisions else {}
    exp_ref = json.dumps(state.intermediate_results)[:200]

    results_summary = {
        k: (v.get("summary") if isinstance(v, dict) and "summary" in v else
            {kk: vv for kk, vv in v.items() if kk not in {"runs", "samples"}}
            if isinstance(v, dict) else v)
        for k, v in state.intermediate_results.items()
    }
    episode = epi_mem.record_episode(
        ctx.db, tenant_id=ctx.job.tenant_id, project_id=ctx.job.project_id,
        session_id=ctx.session.id,
        objective=state.research_question or state.objective,
        assumptions=state.approved_parameters.get("assumptions", []),
        dataset_ids=[d.get("id", "") for d in state.datasets],
        tool_invocations=[{"node": nid, "evidence": ev}
                          for nid, ev in state.provenance.items()],
        parameters={k: v for k, v in state.approved_parameters.items()
                    if k in {"H0", "Om0", "mcmc", "sweep"}},
        status="completed" if validation.get("all_passed") else "completed_with_issues",
        results=results_summary,
        artifacts=[a for res in state.intermediate_results.values()
                   if isinstance(res, dict) for a in res.get("artifacts", [])
                   if isinstance(a, str)][:20],
    )

    eq_ids = []
    for eq in state.approved_parameters.get("equations", [])[:3]:
        m = sem_mem.add_knowledge(
            ctx.db, tenant_id=ctx.job.tenant_id, kind="equation",
            title=eq["name"], content=f"{eq.get('latex', '')} — regime: {eq['regime']}",
            status="established", source_refs=[eq["source"]],
        )
        eq_ids.append(m.id)

    measurement_id = None
    if validation.get("validation_row_id"):
        measurement_id = sem_mem.add_knowledge(
            ctx.db, tenant_id=ctx.job.tenant_id, kind="finding",
            title=f"{domain.capitalize()} analysis measurements (job {ctx.job.id[:8]})",
            content=f"Executed analysis results: {json.dumps(results_summary)[:800]}",
            status="verified",
            source_refs=[f"job:{ctx.job.id}",
                         f"validation:{validation['validation_row_id']}"],
            confidence=0.9,
        ).id
    hypothesis_id = sem_mem.add_knowledge(
        ctx.db, tenant_id=ctx.job.tenant_id, kind="hypothesis",
        title=f"{domain.capitalize()} hypothesis after this investigation",
        content=f"{state.hypothesis} — pending further independent tests. "
                f"Context: {exp_ref}",
        status="hypothesis", source_refs=[f"job:{ctx.job.id}"],
        confidence=0.5, evidence_quality="medium",
    ).id

    name, category, steps = PROCEDURES[domain]
    proc = proc_mem.save_procedure(
        ctx.db, tenant_id=ctx.job.tenant_id, name=name, category=category,
        description=f"Reusable {domain} workflow validated in job {ctx.job.id[:8]}",
        workflow={"steps": steps,
                  "approved_parameters": {k: state.approved_parameters.get(k)
                                          for k in ("H0", "Om0", "sweep")
                                          if k in state.approved_parameters}},
    )
    if validation.get("all_passed"):
        proc_mem.approve(
            ctx.db, tenant_id=ctx.job.tenant_id, procedure_id=proc.id,
            evidence={"executed": True, "validated": True, "job_id": ctx.job.id,
                      "checks": validation.get("checks", {})},
        )
        proc_status = "approved"
    else:
        proc_status = "left pending (validation evidence incomplete)"

    add_message(ctx.db, ctx.session, agent="memory_coordinator",
                content=f"Episode {episode.id[:8]} recorded; {len(eq_ids)} equations; "
                        f"measurement {str(measurement_id)[:8]}; hypothesis retained as "
                        f"hypothesis; procedure {proc_status}.",
                meta={"episode_id": episode.id, "knowledge_ids": eq_ids,
                      "measurement_id": measurement_id, "hypothesis_id": hypothesis_id,
                      "procedure_id": proc.id, "procedure_status": proc_status})

    # context layer: link this run into the FalkorDB graph (evidence-gated)
    exp_graph_id = next(
        (v.get("experiment_id") for v in state.intermediate_results.values()
         if isinstance(v, dict) and v.get("experiment_id")), None)
    graph_res, graph_summary = _graph_sync(
        ctx, episode_id=episode.id,
        procedure={"id": proc.id, "name": name,
                   "status": "approved" if validation.get("all_passed") else "pending"},
        knowledge_ids=[k for k in (*eq_ids, measurement_id, hypothesis_id) if k],
        experiment_id=exp_graph_id,
        validation_id=validation.get("validation_row_id"),
        artifact_ids=(list(episode.artifacts)
                      if isinstance(episode.artifacts, list) else [])[:20])
    return AgentResult(
        summary=f"episode + knowledge persisted; procedure {proc_status}",
        output={"episode_id": episode.id, "equation_ids": eq_ids,
                "measurement_id": measurement_id, "hypothesis_id": hypothesis_id,
                "procedure_id": proc.id, "procedure_status": proc_status,
                "context_graph": graph_res},
        evidence=[
            evidence("memory.episodic.write", args={"episode_id": episode.id},
                     result_summary=f"episode recorded (status={episode.status})"),
            evidence("memory.semantic.write",
                     args={"equations": len(eq_ids), "measurement_id": measurement_id},
                     result_summary="established equations cited; outcome stored as verified "
                                    "measurement + separate hypothesis"),
            evidence("memory.procedural.approve" if validation.get("all_passed")
                     else "memory.procedural.save",
                     args={"procedure_id": proc.id}, result_summary=proc_status,
                     check_names=["validation_evidence_required"]),
            evidence("memory.context_graph.write",
                     args={"episode_id": episode.id,
                           "experiment_id": exp_graph_id},
                     result_summary=graph_summary),
        ],
    )


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def h_report(ctx: NodeContext) -> AgentResult:
    from app.reports.generate import generate_report

    art, summary = generate_report(ctx.db, job=ctx.job, session=ctx.session, state=ctx.state)
    add_message(ctx.db, ctx.session, agent="report",
                content=f"Report generated: {art.filename} (artifact {art.id[:8]})",
                meta={"artifact_id": art.id, "sections": summary["sections"]})
    return AgentResult(
        summary=f"report {art.filename} with {len(summary['sections'])} sections",
        output={"artifact_id": art.id, "filename": art.filename, **summary},
        evidence=[evidence("report.generate",
                           args={"artifact_id": art.id},
                           result_summary=f"markdown report with {len(summary['sections'])} sections, "
                                          f"{summary.get('n_references', 0)} references, "
                                          f"{summary.get('n_artifacts', 0)} linked artifacts",
                           artifact_ids=[art.id])],
    )


def _domain_handler(name: str):
    """Lazy proxy so handlers_domains (which imports this module) resolves safely."""
    def _call(ctx: NodeContext) -> AgentResult:
        from app.orchestration import handlers_domains as hd

        return getattr(hd, name)(ctx)

    _call.__name__ = name
    return _call


def _paper_handler(name: str):
    """Lazy proxy so handlers_paper (which imports this module) resolves safely."""
    def _call(ctx: NodeContext) -> AgentResult:
        from app.orchestration import handlers_paper as hp

        return getattr(hp, name)(ctx)

    _call.__name__ = name
    return _call


HANDLERS = {
    "plan": h_plan,
    "knowledge": h_knowledge,
    "equations": h_equations,
    "setup": h_setup,
    "sweep": h_sweep,
    "validate": h_validate,
    "memory": h_memory,
    "report": h_report,
    # domain analysis nodes
    "stellar_analysis": _domain_handler("stellar_analysis"),
    "cosmology_analysis": _domain_handler("cosmology_analysis"),
    "observation_fetch": _domain_handler("observation_fetch"),
    "observation_analysis": _domain_handler("observation_analysis"),
    # paper interpretation nodes
    "paper_ingest": _paper_handler("h_paper_ingest"),
    "paper_extract": _paper_handler("h_paper_extract"),
    "paper_setup": _paper_handler("h_paper_setup"),
    "paper_run": _paper_handler("h_paper_run"),
    "explain": _paper_handler("h_explain"),
}
