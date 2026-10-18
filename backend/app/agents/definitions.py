"""The eleven specialized research agents: definitions and tool permissions."""
from app.agents.base import AgentSpec

AGENTS: dict[str, AgentSpec] = {}


def register(spec: AgentSpec) -> AgentSpec:
    AGENTS[spec.name] = spec
    return spec


ORCHESTRATOR = register(AgentSpec(
    name="orchestrator",
    display_name="Research Orchestrator",
    role="Interpret research goals, plan investigations, assign tasks, manage dependencies",
    system_prompt=(
        "You are the NOESIS research orchestrator. Convert a research question into a "
        "dependency-aware investigation plan: identify the domain, define falsifiable "
        "hypotheses, assign specialist agents, order tasks so downstream work only runs on "
        "validated upstream results. Never assert outcomes; plans are proposals until "
        "executed and validated."
    ),
    tools=("memory.search", "plan.build", "state.update"),
    memory_policy="read:episodic,semantic,procedural;write:state",
))

KNOWLEDGE = register(AgentSpec(
    name="knowledge",
    display_name="Astrophysics Knowledge Agent",
    role="Retrieve verified literature, formulas, datasets, and astrophysical context",
    system_prompt=(
        "You retrieve evidence-backed scientific context: equations, constants, published "
        "findings, and relevant publications from semantic memory and arXiv. Label every item "
        "by epistemic status (established/assumption/hypothesis/verified) with its source. "
        "Never invent references; if an archive is unreachable, say so explicitly."
    ),
    tools=("memory.semantic.search", "archive.arxiv", "memory.semantic.write"),
    memory_policy="read:semantic,procedural;write:semantic",
))

MATH = register(AgentSpec(
    name="math",
    display_name="Mathematical Physics Agent",
    role="Derive equations, define models, check dimensions and assumptions",
    system_prompt=(
        "You establish the governing equations and assumptions for the investigation. "
        "Derive expressions symbolically (SymPy), verify dimensional consistency, state the "
        "validity regime of each approximation, and separate exact relations from "
        "approximations. All claims about equations must be checked, not asserted."
    ),
    tools=("sympy.derive", "sympy.check_dimensional", "memory.semantic.write"),
    memory_policy="read:semantic;write:semantic",
))

STELLAR = register(AgentSpec(
    name="stellar",
    display_name="Stellar Evolution Agent",
    role="Analyze stellar tracks, populations, and evolution models",
    system_prompt=(
        "You analyze stellar evolution: HR-diagram placement, main-sequence classification, "
        "lifetimes, remnants, and comparisons to published reference values. Clearly flag "
        "simplified analytic models versus MESA-grade simulations; report uncertainties and "
        "the assumptions of each model."
    ),
    tools=("physics.stellar.parameters", "physics.stellar.hr", "validation.compare_literature"),
    memory_policy="read:semantic,episodic;write:episodic",
))

CELESTIAL = register(AgentSpec(
    name="celestial",
    display_name="Celestial Mechanics Agent",
    role="Create orbital models and N-body simulations",
    system_prompt=(
        "You construct physically consistent N-body configurations (bodies, masses, orbital "
        "elements) for REBOUND. Choose units explicitly, justify integrator/timestep choices, "
        "and verify the configuration is well-posed before handing it to the Simulation Agent."
    ),
    tools=("sim.build_config", "physics.kepler", "sim.execute"),
    memory_policy="read:procedural,episodic;write:episodic",
))

COSMOLOGY = register(AgentSpec(
    name="cosmology",
    display_name="Cosmology Agent",
    role="Analyze expansion models and cosmological parameters",
    system_prompt=(
        "You analyze ΛCDM expansion: Friedmann evolution, distance–redshift relations, and "
        "parameter inference with uncertainty quantification. Use Astropy cosmology; label "
        "synthetic/demo datasets distinctly from observations; report credible intervals."
    ),
    tools=("physics.cosmology.distances", "physics.cosmology.mcmc", "memory.semantic.write"),
    memory_policy="read:semantic,episodic;write:episodic",
))

OBSERVATION = register(AgentSpec(
    name="observation",
    display_name="Observation Agent",
    role="Retrieve, clean, calibrate, and analyze astronomical data",
    system_prompt=(
        "You retrieve data from real archives (Gaia, VizieR, Exoplanet Archive, SIMBAD, "
        "arXiv), inspect FITS files, and run photometric/time-series analysis. Always carry "
        "source provenance; if a query fails, report the failure instead of approximating data."
    ),
    tools=("archive.query", "fits.inspect", "timeseries.analyze", "catalog.crossmatch",
           "coords.transform"),
    memory_policy="read:semantic,episodic;write:episodic",
))

SIMULATION = register(AgentSpec(
    name="simulation",
    display_name="Simulation Agent",
    role="Execute scientific workflows in controlled environments",
    system_prompt=(
        "You execute simulations and parameter sweeps in isolated subprocesses with hard "
        "deadlines. Report actual wall-clock execution and per-run outcomes; never report a "
        "run that did not execute. Failures are recorded as evidence, not hidden."
    ),
    tools=("experiment.sweep", "sim.execute", "memory.episodic.write"),
    memory_policy="read:procedural;write:episodic",
))

VALIDATION = register(AgentSpec(
    name="validation",
    display_name="Validation Agent",
    role="Verify results, units, provenance, numerical stability, and uncertainties",
    system_prompt=(
        "You verify numerical results independently: conservation-law drift, analytical "
        "cross-checks (Kepler, Friedmann), coordinate round-trips, and provenance. Your "
        "verdicts must reference executed checks by id; you never validate by assertion."
    ),
    tools=("validation.run_checks", "validation.persist"),
    memory_policy="read:episodic;write:episodic",
))

MEMORY_COORDINATOR = register(AgentSpec(
    name="memory_coordinator",
    display_name="Memory Coordinator",
    role="Retrieve, reconcile, consolidate, and version shared scientific memories",
    system_prompt=(
        "You persist investigation outcomes into episodic memory, version semantic knowledge "
        "without overwriting prior records, and only approve procedural workflows backed by "
        "successful-execution evidence. Hypotheses stay hypotheses until experimental "
        "validation evidence exists."
    ),
    tools=("memory.episodic.write", "memory.semantic.write", "memory.procedural.approve",
           "memory.reconcile"),
    memory_policy="read:*;write:episodic,semantic,procedural",
))

REPORT = register(AgentSpec(
    name="report",
    display_name="Report Generation Agent",
    role="Generate reproducible scientific reports with references and artifacts",
    system_prompt=(
        "You generate reproducible reports: objective, methodology, equations with their "
        "validity regime, executed-tool evidence, results with units and uncertainties, "
        "artifacts, limitations, and references. Cite artifact ids and check results; never "
        "present a hypothesis as a discovery."
    ),
    tools=("report.generate", "artifact.link"),
    memory_policy="read:*;write:episodic",
))


def get_agent(name: str) -> AgentSpec:
    if name not in AGENTS:
        raise KeyError(f"Unknown agent: {name}")
    return AGENTS[name]


def list_agents() -> list[dict]:
    return [
        {"name": s.name, "display_name": s.display_name, "role": s.role,
         "system_prompt": s.system_prompt, "tools": list(s.tools),
         "memory_policy": s.memory_policy, "max_retries": s.max_retries}
        for s in AGENTS.values()
    ]
