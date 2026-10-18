"""Node handlers for the paper-interpretation research domain.

The multi-step interpretation of a research paper runs through the same
durable orchestration graph as every other investigation: each node performs
real tool work (fetching metadata from documented APIs, executing this
platform's physics engines) and returns evidence; the graph rejects any node
that produces none. Narrative text is a deterministic template over executed
results — numbers come only from tools, never from prose.
"""
import json
import time

from app.agents.base import AgentResult, evidence
from app.core.errors import DomainError, ValidationErr
from app.database.models import ValidationResult as VR
from app.orchestration.graph import NodeContext
from app.orchestration.handlers import add_message


def _paper_state(ctx: NodeContext) -> dict:
    return ctx.state.intermediate_results.setdefault("paper", {})


def _paper_url(ctx: NodeContext) -> str:
    return (ctx.state.approved_parameters.get("paper_url")
            or ctx.state.research_question.replace("Interpret paper", "").strip())


# --------------------------------------------------------------------------- #
# ingest: real metadata fetch (arXiv API / Crossref), explicit failure path
# --------------------------------------------------------------------------- #

def h_paper_ingest(ctx: NodeContext) -> AgentResult:
    from app.physics.paper.ingest import fetch_paper, parse_paper_ref

    t0 = time.time()
    url = _paper_url(ctx)
    ref = parse_paper_ref(url)  # ValidationErr -> node fails honestly
    paper = fetch_paper(ref)    # DomainError -> retries then honest failure

    if not paper.get("abstract"):
        raise DomainError(
            f"Paper {ref['id']} has no abstract in the source metadata — "
            "cannot extract claims without one (full-text PDF parsing is out of scope)")

    paper_state = _paper_state(ctx)
    paper_state["paper"] = paper
    paper_state["ref"] = ref
    ctx.state.datasets.append({
        "id": f"paper:{ref['kind']}:{ref['id']}",
        "kind": "paper_metadata",
        "source": paper["source"],
        "title": paper["title"],
        "url": paper["url"],
        "fetched_via": ref["kind"],
    })
    authors = paper.get("authors", [])
    author_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
    add_message(ctx.db, ctx.session, agent="knowledge",
                content=f"Paper fetched: “{paper['title']}” ({author_str}; {paper['source']}). "
                        f"Abstract {len(paper['abstract'])} chars.",
                meta={"ref": ref, "title": paper["title"]})
    return AgentResult(
        summary=f"fetched {ref['kind']} metadata: {paper['title'][:80]}",
        output={"ref": ref, "title": paper["title"],
                "authors": authors[:10], "published": paper.get("published", ""),
                "abstract_chars": len(paper["abstract"])},
        evidence=[evidence(f"archive.{ref['kind']}.fetch",
                           args={"id": ref["id"]},
                           result_summary=f"title={paper['title'][:150]}; "
                                          f"{len(authors)} authors; abstract {len(paper['abstract'])} chars "
                                          f"from {paper['source']}",
                           duration_s=time.time() - t0)],
    )


# --------------------------------------------------------------------------- #
# extract: deterministic regex parse of the abstract, verbatim snippets
# --------------------------------------------------------------------------- #

def h_paper_extract(ctx: NodeContext) -> AgentResult:
    from app.physics.paper.ingest import detect_subdomain, extract_quantities, find_object_names

    t0 = time.time()
    paper_state = _paper_state(ctx)
    paper = paper_state["paper"]
    blob = f"{paper['title']} {paper['abstract']}"

    quantities = extract_quantities(blob)
    subdomain, scores = detect_subdomain(paper["title"], paper["abstract"])
    object_names = find_object_names(blob)

    paper_state["quantities"] = quantities
    paper_state["subdomain"] = subdomain
    paper_state["subdomain_scores"] = scores
    paper_state["object_names"] = object_names
    paper_state["extraction_scope"] = "abstract + title only (regex; full text not parsed)"

    list_str = "; ".join(f"{q['kind']}={q['value']:g} {q['unit']}" for q in quantities) or "none"
    add_message(ctx.db, ctx.session, agent="math",
                content=f"Extracted {len(quantities)} quantitative claim(s) verbatim from the "
                        f"abstract: {list_str}. Sub-domain → {subdomain} (scores {scores}).",
                meta={"quantities": quantities, "subdomain": subdomain,
                      "scores": scores, "object_names": object_names})
    return AgentResult(
        summary=f"{len(quantities)} claims extracted; sub-domain {subdomain}",
        output={"n_quantities": len(quantities), "quantities": quantities,
                "subdomain": subdomain, "scores": scores,
                "object_names": object_names},
        evidence=[evidence("paper.extract_quantities",
                           args={"abstract_chars": len(blob),
                                 "kinds": [q["kind"] for q in quantities]},
                           result_summary=("claims (verbatim snippets retained): "
                                           + json.dumps([{k: q[k] for k in ("kind", "value", "unit")}
                                                         for q in quantities])[:400]),
                           duration_s=time.time() - t0)],
    )


# --------------------------------------------------------------------------- #
# setup: map claims onto concrete engine runs (defaults declared, never silent)
# --------------------------------------------------------------------------- #

def h_paper_setup(ctx: NodeContext) -> AgentResult:
    from app.physics.paper.ingest import build_proposals

    t0 = time.time()
    paper_state = _paper_state(ctx)
    proposals = build_proposals(paper_state["subdomain"], paper_state["quantities"],
                                paper_state["object_names"])

    if not proposals:
        raise DomainError(
            "No engine mapping available for this paper: sub-domain "
            f"'{paper_state['subdomain']}' with extracted quantities "
            f"{[q['kind'] for q in paper_state['quantities']]} and object names "
            f"{paper_state['object_names']} produced zero runnable simulations. "
            "This platform maps stellar (PARSEC), cosmology (ΛCDM ladder) and "
            "two-body orbital claims onto engines; other claims are reported "
            "as extracted but not simulated.")

    ctx.state.simulation_configs["paper"] = {
        "proposals": proposals,
        "subdomain": paper_state["subdomain"],
        "declared_defaults": [
            p["justification"] for p in proposals
            if not all(p.get("from_paper", {}).values())
        ],
    }
    ctx.state.approved_parameters["assumptions"] = [
        "Quantities extracted from the abstract only (full text not parsed)",
        "Parameters absent from the abstract use platform defaults, declared per proposal",
        f"Sub-domain mapping: {paper_state['subdomain']} (keyword-scored from title+abstract)",
        "Reproduction runs this platform's engines, not the paper's own pipelines",
    ]
    paper_state["proposals"] = proposals

    mapping = "; ".join(f"{p['id']}→{p['engine']}" for p in proposals)
    add_message(ctx.db, ctx.session, agent="orchestrator",
                content=f"Mapped claims to {len(proposals)} engine run(s): {mapping}. "
                        "Parameters not stated in the abstract use declared platform "
                        "defaults (listed per proposal).",
                meta={"proposals": proposals})
    return AgentResult(
        summary=f"{len(proposals)} engine proposal(s) mapped from extracted claims",
        output={"n_proposals": len(proposals),
                "engines": [p["engine"] for p in proposals]},
        evidence=[evidence("paper.map_to_engines",
                           args={"n_proposals": len(proposals),
                                 "subdomain": paper_state["subdomain"]},
                           result_summary=mapping + " | defaults: "
                           + json.dumps({p["id"]: p["from_paper"] for p in proposals})[:300],
                           duration_s=time.time() - t0)],
    )


# --------------------------------------------------------------------------- #
# run: execute each proposal on a real engine; errors recorded per proposal
# --------------------------------------------------------------------------- #

def _run_cosmology(params: dict) -> dict:
    import numpy as np

    from app.physics.cosmology.model import distance_ladder, make_cosmology

    z_max = float(params["z_max"])
    z = np.linspace(0.0, z_max, 30)
    ladder = distance_ladder(z, H0=float(params["H0"]), Om0=float(params["Om0"]))
    cosmo = make_cosmology(H0=float(params["H0"]), Om0=float(params["Om0"]))
    age_now = float(cosmo.age(0.0).to("Gyr").value)
    i_z1 = int(np.argmin(np.abs(z - 1.0)))
    return {
        "engine": "cosmology.distance_ladder",
        "headline": {
            "age_now_Gyr": age_now,
            "luminosity_distance_z1_Mpc": float(ladder["luminosity_distance_Mpc"][i_z1]),
            "comoving_distance_zmax_Mpc": float(ladder["comoving_distance_Mpc"][-1]),
            "H0_km_s_Mpc": float(params["H0"]),
            "Om0": float(params["Om0"]),
            "z_max": z_max,
        },
        "detail": {"n_redshifts": len(z),
                   "reference": ladder.get("reference", ""),
                   "age_Gyr_at_z": ladder["age_Gyr"]},
        "fidelity": "astropy FlatLambdaCDM (numerical, published implementation)",
    }


def _run_stellar(params: dict) -> dict:
    from app.physics.stellar.tracks import point_parameters

    kwargs = {"metallicity_z": float(params.get("metallicity_z", 0.014))}
    age = params.get("age_yr")
    pt = point_parameters(float(params["mass_msun"]),
                          age_yr=float(age) if age else None, **kwargs)
    return {
        "engine": "stellar.point_parameters",
        "headline": {
            "mass_msun": float(params["mass_msun"]),
            "teff_K": float(pt["teff_K"]),
            "luminosity_msun": float(pt["luminosity_msun"]),
            "radius_msun": float(pt["radius_msun"]),
            "spectral_class": pt["spectral_class"],
            "age_yr": float(pt["age_yr"]),
            "ms_lifetime_Gyr_proxy": float(pt["ms_lifetime_Gyr_proxy"]),
        },
        "detail": {"age_note": pt.get("age_note", ""),
                   "model_fidelity": pt["model_fidelity"],
                   "provenance_dataset": pt["provenance"]["dataset"]},
        "fidelity": pt["model_fidelity"],
    }


def _run_celestial(params: dict) -> dict:
    from app.physics.celestial.kepler import orbital_period_yr
    from app.physics.celestial.rebound_engine import run_simulation
    from app.physics.celestial.types import BodySpec, SimConfig, SimulationRequest

    a_au = params.get("a_au")
    period_days = params.get("period_days")
    m_star = float(params.get("m_star_msun") or 1.0)
    m_planet = float(params.get("m_planet_msun") or 1e-3)

    if not a_au and period_days:
        # derive a from P via Kepler's third law (P in yr, M in Msun -> a in AU)
        p_yr = float(period_days) / 365.25
        a_au = (m_star * p_yr ** 2) ** (1 / 3)
    if not a_au:
        raise ValidationErr("orbital proposal has neither semi-major axis nor period")

    p_yr = orbital_period_yr(m_star + m_planet, float(a_au))
    t_end = min(max(5.0 * p_yr, 1e-3), 20.0)
    req = SimulationRequest(
        bodies=[
            BodySpec(name="star", mass_value=m_star, mass_unit="msun",
                     x=0, y=0, z=0, vx=0, vy=0, vz=0),
            BodySpec(name="planet", mass_value=m_planet, mass_unit="msun",
                     a=float(a_au), e=float(params.get("e", 0.0))),
        ],
        config=SimConfig(integrator="ias15", dt=min(0.01, p_yr / 100),
                         t_end=t_end, output_every=50),
    )
    out = run_simulation(req)
    diag = out["diagnostics"]
    return {
        "engine": "celestial.rebound_two_body",
        "status": out["status"],
        "headline": {
            "a_au": float(a_au),
            "period_days": float(p_yr * 365.25),
            "t_end_yr": float(t_end),
            "energy_drift_rel_max": float(diag["energy_drift_rel_max"]),
            "angmom_drift_rel_max": float(diag["angmom_drift_rel_max"]),
            "n_snapshots": int(out["meta"]["n_snapshots"]),
        },
        "detail": {"integrator": out["meta"]["integrator"],
                   "rebound_version": out["meta"]["rebound_version"],
                   "status": out["status"]},
        "fidelity": "REBOUND IAS15 (real N-body integration)",
    }


def _run_simbad(params: dict) -> dict:
    from app.physics.observations.connectors import resolve_simbad

    res = resolve_simbad(str(params["object_name"]))
    flat = {k: v for k, v in res.items()
            if isinstance(v, (int, float, str, bool)) or
            (isinstance(v, list) and len(json.dumps(v, default=str)) < 400)}
    return {
        "engine": "observation.simbad_resolve",
        "headline": flat,
        "detail": {"raw_keys": sorted(res.keys())},
        "fidelity": "live SIMBAD name-service query (archive)",
    }


_RUNNERS = {
    "cosmology.distance_ladder": _run_cosmology,
    "stellar.point_parameters": _run_stellar,
    "celestial.rebound_two_body": _run_celestial,
    "observation.simbad_resolve": _run_simbad,
}


def h_paper_run(ctx: NodeContext) -> AgentResult:
    from app.core.artifacts import save_json_artifact

    t0 = time.time()
    paper_state = _paper_state(ctx)
    proposals = ctx.state.simulation_configs["paper"]["proposals"]

    runs: list[dict] = []
    ev: list[dict] = []
    for prop in proposals:
        runner = _RUNNERS.get(prop["engine"])
        entry = {"proposal_id": prop["id"], "engine": prop["engine"],
                 "label": prop["label"], "justification": prop["justification"],
                 "from_paper": prop.get("from_paper", {})}
        if runner is None:
            entry.update(status="failed", error=f"no runner for engine {prop['engine']}")
        else:
            try:
                t_run = time.time()
                res = runner(prop["params"])
                entry.update(res, status="completed")
                ev.append(evidence(prop["engine"],
                                   args=prop["params"],
                                   result_summary=json.dumps(res["headline"], default=str)[:500],
                                   duration_s=time.time() - t_run))
            except Exception as exc:  # recorded honestly; never fabricated
                entry.update(status="failed", error=f"{type(exc).__name__}: {exc}"[:400])
        runs.append(entry)

    completed = [r for r in runs if r["status"] == "completed"]
    if not completed:
        detail = "; ".join(f"{r['proposal_id']}: {r.get('error', '?')}" for r in runs)
        raise DomainError(f"Every mapped engine run failed — {detail}")

    art = save_json_artifact(
        ctx.db, tenant_id=ctx.job.tenant_id, kind="paper_findings",
        filename="paper_findings.json",
        payload={"paper": paper_state["paper"], "quantities": paper_state["quantities"],
                 "runs": runs},
        project_id=ctx.job.project_id, session_id=ctx.session.id,
        meta={"n_runs": len(runs), "n_completed": len(completed)},
    )
    paper_state["runs"] = runs
    paper_state["findings_artifact_id"] = art.id
    ctx.state.completed_analyses.append({
        "analysis": "paper_engine_runs", "artifact_id": art.id,
        "n_runs": len(runs), "n_completed": len(completed),
    })

    headline_lines = []
    for r in completed:
        hl = ", ".join(f"{k}={v}" for k, v in list(r["headline"].items())[:6])
        headline_lines.append(f"{r['label']}: {hl}")
    failed = [r for r in runs if r["status"] != "completed"]
    add_message(ctx.db, ctx.session, agent="simulation",
                content=f"Executed {len(completed)}/{len(runs)} mapped simulation(s).\n"
                        + "\n".join(headline_lines)
                        + (("\nFailed (recorded, not hidden): "
                            + "; ".join(f"{r['proposal_id']} — {r.get('error')}" for r in failed))
                           if failed else ""),
                meta={"artifact_id": art.id,
                      "runs": [{k: r[k] for k in ("proposal_id", "engine", "status")} for r in runs]})
    ev.append(evidence("paper.persist_findings",
                       args={"artifact_id": art.id},
                       result_summary=f"{len(completed)}/{len(runs)} engine runs persisted to "
                                      f"paper_findings.json ({len(failed)} failed honestly recorded)",
                       artifact_ids=[art.id]))
    return AgentResult(
        summary=f"{len(completed)}/{len(runs)} engine runs completed",
        output={"n_runs": len(runs), "n_completed": len(completed),
                "artifact_id": art.id,
                "runs": [{k: r.get(k) for k in ("proposal_id", "engine", "status", "headline")}
                         for r in runs]},
        evidence=ev,
    )


# --------------------------------------------------------------------------- #
# validate: independent cross-checks of claims vs executed computation
# --------------------------------------------------------------------------- #

def validate_paper(ctx: NodeContext) -> AgentResult:
    t0 = time.time()
    paper_state = _paper_state(ctx)
    quantities = paper_state.get("quantities", [])
    runs = paper_state.get("runs", [])
    by_kind = {q["kind"]: q for q in quantities}
    rows = []

    def add(name: str, passed: bool, metrics: dict, details: str) -> None:
        vr = VR(tenant_id=ctx.job.tenant_id, job_id=ctx.job.id, check_name=name,
                passed=bool(passed), metrics=metrics, details=details)
        ctx.db.add(vr)
        rows.append(vr)

    # 1. every extracted claim must carry its verbatim snippet (traceability)
    traceable = all(q.get("snippet") for q in quantities) and len(quantities) > 0
    add("paper_claims_traceable", traceable,
        {"n_quantities": len(quantities),
         "kinds": [q["kind"] for q in quantities],
         "scope": paper_state.get("extraction_scope", "")},
        "each extracted number links to the literal abstract text it came from")

    # 2. executed runs agree with a fresh re-execution (determinism)
    repro_ok, repro_metrics = True, {}
    for r in runs:
        if r["status"] != "completed" or r["engine"] not in _RUNNERS:
            continue
        try:
            again = _RUNNERS[r["engine"]](next(
                p["params"] for p in ctx.state.simulation_configs["paper"]["proposals"]
                if p["id"] == r["proposal_id"]))
            same = all(
                abs(float(r["headline"][k]) - float(again["headline"][k]))
                <= 1e-9 * max(1.0, abs(float(r["headline"][k])))
                for k in r["headline"]
                if isinstance(r["headline"].get(k), (int, float))
                and isinstance(again["headline"].get(k), (int, float)))
            repro_metrics[r["proposal_id"]] = same
            repro_ok = repro_ok and same
        except Exception as exc:
            repro_metrics[r["proposal_id"]] = f"re-run failed: {exc}"[:120]
            repro_ok = False
    if runs:
        add("paper_runs_reproducible", repro_ok, repro_metrics,
            "fresh engine re-execution reproduces stored headline numbers")

    # 3. Kepler cross-check: paper's a and P vs Newton's law (only when both given)
    if "semi_major_axis_au" in by_kind and "orbital_period_days" in by_kind:
        from app.physics.celestial.kepler import orbital_period_yr

        m_star = float(by_kind["stellar_mass"]["value"]) if "stellar_mass" in by_kind else 1.0
        a = float(by_kind["semi_major_axis_au"]["value"])
        p_paper_yr = float(by_kind["orbital_period_days"]["value"]) / 365.25
        p_kepler_yr = orbital_period_yr(m_star, a)
        rel = abs(p_kepler_yr - p_paper_yr) / p_paper_yr
        # tolerance widens when the central mass had to be assumed (not in paper)
        tol = 0.05 if "stellar_mass" in by_kind else 0.25
        add("paper_kepler_crosscheck", rel <= tol,
            {"a_au": a, "P_paper_yr": p_paper_yr, "P_kepler_yr": p_kepler_yr,
             "rel_diff": rel, "tolerance": tol, "m_star_msun": m_star,
             "mass_from_paper": "stellar_mass" in by_kind},
            "Kepler's third law from the paper's (a, P); tolerance widens when "
            "the central mass is an assumed 1 M☉ default")

    # 4. cosmology sanity: computed age of the universe at z=0 must be physical
    for r in runs:
        if r["status"] == "completed" and r["engine"] == "cosmology.distance_ladder":
            age = float(r["headline"]["age_now_Gyr"])
            add("paper_cosmology_age_physical", 10.0 <= age <= 16.0,
                {"age_now_Gyr": age, "H0": r["headline"]["H0_km_s_Mpc"],
                 "Om0": r["headline"]["Om0"]},
                "flat ΛCDM age at the paper's parameters within 10–16 Gyr "
                "(consistent with independent age determinations)")

    # 5. N-body conservation laws must hold for any executed integration
    for r in runs:
        if r["status"] == "completed" and r["engine"] == "celestial.rebound_two_body":
            ok = (r["headline"]["energy_drift_rel_max"] < 1e-6
                  and r["status"] == "completed")
            add("paper_orbit_conservation", ok,
                {"energy_drift_rel_max": r["headline"]["energy_drift_rel_max"],
                 "angmom_drift_rel_max": r["headline"]["angmom_drift_rel_max"],
                 "tolerance": 1e-6},
                "IAS15 integration conserves energy to <1e-6 relative drift")

    ctx.db.commit()
    all_pass = bool(rows) and all(r.passed for r in rows)
    ctx.state.validation_decisions.append({
        "domain": "paper", "all_passed": all_pass,
        "checks": {r.check_name: r.passed for r in rows},
        "validation_row_id": rows[0].id if rows else "",
        "tolerances": "traceability strict; reproducibility 1e-9; Kepler 5% (25% if "
                      "mass assumed); ΛCDM age 10–16 Gyr; orbit energy drift <1e-6",
    })
    add_message(ctx.db, ctx.session, agent="validation",
                content=f"Paper validation: {'VALIDATED' if all_pass else 'ISSUES'} "
                        f"({len(rows)} checks) — "
                        + ", ".join(f"{r.check_name}={'pass' if r.passed else 'FAIL'}"
                                    for r in rows),
                meta={"checks": {r.check_name: r.passed for r in rows}})
    return AgentResult(
        summary=f"{'VALIDATED' if all_pass else 'ISSUES'} ({len(rows)} checks)",
        output={"all_passed": all_pass,
                "checks": {r.check_name: r.passed for r in rows},
                "validation_row_id": rows[0].id if rows else ""},
        evidence=[evidence("validation.run_checks", args={"domain": "paper"},
                           result_summary=f"{len(rows)} persisted checks: "
                                          + json.dumps({r.check_name: r.passed for r in rows}),
                           check_names=[r.check_name for r in rows],
                           duration_s=time.time() - t0)],
    )


# --------------------------------------------------------------------------- #
# explain: deterministic plain-language interpretation over executed results
# --------------------------------------------------------------------------- #

_KIND_TEXT = {
    "hubble_constant": "expansion rate (H₀)",
    "omega_m": "matter density (Ω_m)",
    "redshift": "redshift (z)",
    "stellar_mass": "stellar mass",
    "planet_mass_jup": "planet mass (Jupiter masses)",
    "planet_mass_earth": "planet mass (Earth masses)",
    "orbital_period_days": "orbital period",
    "semi_major_axis_au": "semi-major axis",
    "teff": "effective temperature",
    "age_gyr": "age",
    "distance_pc": "distance",
}


def h_explain(ctx: NodeContext) -> AgentResult:
    from app.core.artifacts import save_json_artifact
    from app.core.glossary import find_terms

    t0 = time.time()
    paper_state = _paper_state(ctx)
    paper = paper_state.get("paper", {})
    quantities = paper_state.get("quantities", [])
    runs = paper_state.get("runs", [])
    val = ctx.state.validation_decisions[-1] if ctx.state.validation_decisions else {}

    # -- section 1: what the paper says (verbatim metadata, no paraphrase) --
    authors = paper.get("authors", [])
    s_paper = [
        f"“{paper.get('title', '?')}” — {', '.join(authors[:3])}"
        + (f" and {len(authors) - 3} co-authors" if len(authors) > 3 else "")
        + f" ({paper.get('published') or 'date n/a'}), via {paper.get('source', '?')}.",
        f"Abstract (verbatim): {paper.get('abstract', '')[:700]}"
        + ("…" if len(paper.get("abstract", "")) > 700 else ""),
    ]

    # -- section 2: what we understood from it (each number + its snippet) --
    if quantities:
        s_extract = [
            f"The abstract states {_KIND_TEXT.get(q['kind'], q['kind'])} = "
            f"{q['value']:g} {q['unit']} — matched text: “…{q['snippet']}…”"
            for q in quantities
        ]
    else:
        s_extract = ["No quantitative claims were found in the abstract; "
                     "only qualitative interpretation follows."]

    # -- section 3: what we ran, and where every parameter came from --
    if runs:
        s_run = []
        for r in runs:
            if r["status"] != "completed":
                s_run.append(f"{r['label']} — FAILED: {r.get('error', 'unknown error')} "
                             "(recorded as a failure, not hidden)")
                continue
            src = ", ".join(f"{k}={'from paper' if v else 'platform default'}"
                            for k, v in r.get("from_paper", {}).items()) or "from paper"
            hl = "; ".join(f"{k} = {v}" for k, v in r["headline"].items())
            s_run.append(f"{r['label']} [{r['engine']}, {r.get('fidelity', 'engine output')}] — "
                         f"{hl}. Inputs: {src}.")
    else:
        s_run = ["No simulations were executed for this paper."]

    # -- section 4: findings -- (headline numbers only; artifact has full data)
    completed = [r for r in runs if r["status"] == "completed"]
    s_find = [
        f"{r['label']}: " + ", ".join(f"{k}={v}" for k, v in r["headline"].items())
        for r in completed
    ] or ["Nothing computed yet."]

    # -- section 5: validation verdict --
    checks = val.get("checks", {})
    if checks:
        s_val = [f"{'✅' if ok else '❌'} {name}" for name, ok in checks.items()]
        s_val.append("Verdict: " + ("all checks passed" if val.get("all_passed")
                                    else "one or more checks FAILED — treat the "
                                         "reproduction as partial"))
    else:
        s_val = ["No validation checks recorded."]

    # -- section 6: limitations (honest scope) --
    s_limits = [
        "Claims are extracted from the abstract only — the PDF full text is not parsed.",
        "Paper prose is never simulated: only quantities the engines can consume "
        "(masses, orbits, H₀/Ω_m, positions) are mapped to runs.",
        "Parameters absent from the abstract use declared platform defaults, "
        "labeled per run above.",
        "Engine fidelity labels apply (published PARSEC tracks / astropy / REBOUND); "
        "no result here reproduces the paper's own pipelines.",
        "Validation verdicts cover internal consistency of this reproduction, "
        "not the correctness of the paper's conclusions.",
    ]

    sections = [
        {"heading": "What the paper says", "body": s_paper},
        {"heading": "What we understood from it", "body": s_extract},
        {"heading": "What we ran and why", "body": s_run},
        {"heading": "What we found (executed numbers)", "body": s_find},
        {"heading": "How it checks out", "body": s_val},
        {"heading": "Limits of this interpretation", "body": s_limits},
    ]

    full_text = "\n".join(x for s in sections for x in s["body"])
    glossary_hits = sorted({m["id"] for m in find_terms(full_text)})

    explanation = {
        "sections": sections,
        "glossary_terms": glossary_hits,
        "verdict": ("validated" if val.get("all_passed") else
                    "issues found" if val else "unvalidated"),
        "n_executed_runs": len(completed),
        "deterministic_template": True,
    }
    paper_state["explanation"] = explanation

    art = save_json_artifact(
        ctx.db, tenant_id=ctx.job.tenant_id, kind="paper_explanation",
        filename="paper_explanation.json", payload=explanation,
        project_id=ctx.job.project_id, session_id=ctx.session.id,
        meta={"verdict": explanation["verdict"], "glossary_terms": glossary_hits},
    )

    body_md = "\n".join(f"**{s['heading']}**\n" + "\n".join(f"• {b}" for b in s["body"])
                        for s in sections)
    add_message(ctx.db, ctx.session, agent="orchestrator", content=body_md,
                meta={"artifact_id": art.id, "verdict": explanation["verdict"],
                      "glossary_terms": glossary_hits})
    return AgentResult(
        summary=f"plain-language interpretation written ({explanation['verdict']})",
        output={"artifact_id": art.id, "verdict": explanation["verdict"],
                "glossary_terms": glossary_hits,
                "sections": [s["heading"] for s in sections]},
        evidence=[evidence("paper.explain",
                           args={"n_sections": len(sections)},
                           result_summary=f"{len(sections)} sections over "
                                          f"{len(completed)} executed runs; verdict="
                                          f"{explanation['verdict']}; glossary-linked "
                                          f"terms: {', '.join(glossary_hits[:12])}",
                           artifact_ids=[art.id],
                           check_names=list(checks),
                           duration_s=time.time() - t0)],
    )
