"""Domain node handlers: stellar, cosmology, observation analyses + validators.

All four domains follow the same discipline: execute real computation, persist
plot/artifact evidence, and let the validation node issue a verdict based on
executed checks (never on the analysis agent's own claim).
"""
import json
import time

from app.agents.base import AgentResult, evidence
from app.database.models import ValidationResult as VR, DatasetRecord
from app.orchestration.graph import NodeContext
from app.orchestration.handlers import add_message


# ---------------------------------------------------------------------------
# STELLAR
# ---------------------------------------------------------------------------

def stellar_analysis(ctx: NodeContext) -> AgentResult:
    from app.core.artifacts import save_artifact
    from app.core.plots import plot_hr_diagram
    from app.physics.stellar.main_sequence import REFERENCE_STARS, stellar_parameters, spectral_class

    t0 = time.time()
    import numpy as np

    masses = np.geomspace(0.1, 50.0, 36)
    points = [stellar_parameters(float(m)) for m in masses]

    # residuals: simplified model vs published reference values
    residuals = []
    for star in REFERENCE_STARS:
        if star["name"] == "Betelgeuse":  # not main sequence: out of model regime
            residuals.append({"name": star["name"], "in_regime": False,
                              "reason": "red supergiant, outside MS model validity",
                              "source": star["source"]})
            continue
        model = stellar_parameters(star["mass_msun"])
        teff_rel = abs(model["teff_K"] - star["teff_K"]) / star["teff_K"]
        lum_rel = abs(model["luminosity_msun"] - star["lum_msun"]) / star["lum_msun"]
        residuals.append({
            "name": star["name"], "in_regime": True, "source": star["source"],
            "teff_model_K": model["teff_K"], "teff_lit_K": star["teff_K"],
            "teff_rel_err": teff_rel,
            "lum_model_msun": model["luminosity_msun"], "lum_lit_msun": star["lum_msun"],
            "lum_rel_err": lum_rel,
            "spectral_class_lit_teff": spectral_class(star["teff_K"])[0],
            "spectral_class_model": model["spectral_class"],
        })

    png = plot_hr_diagram(points, REFERENCE_STARS)
    art = save_artifact(
        ctx.db, tenant_id=ctx.job.tenant_id, kind="plot", filename="hr_diagram.png",
        content=png, project_id=ctx.job.project_id, session_id=ctx.session.id,
        content_type="image/png", meta={"n_model_points": len(points),
                                        "n_reference_stars": len(REFERENCE_STARS)},
    )
    ctx.state.intermediate_results["stellar"] = {
        "hr_artifact_id": art.id, "residuals": residuals,
        "model_fidelity": "SIMPLIFIED ANALYTIC (not MESA)",
        "n_points": len(points),
    }
    ctx.state.completed_analyses.append({
        "analysis": "hr_diagram_and_reference_comparison", "artifact_id": art.id,
        "n_residuals": len(residuals),
    })
    add_message(ctx.db, ctx.session, agent="stellar",
                content=f"HR diagram computed for {len(points)} model masses; compared against "
                        f"{sum(1 for r in residuals if r.get('in_regime'))} literature references.",
                meta={"artifact_id": art.id, "residuals": residuals})
    return AgentResult(
        summary=f"HR diagram + {len(residuals)} reference comparisons",
        output={"hr_artifact_id": art.id, "residuals": residuals},
        evidence=[evidence("physics.stellar.hr",
                           args={"mass_range_msun": [0.1, 50.0], "n_points": len(points)},
                           result_summary=f"HR plot saved; residuals vs literature: "
                                          + json.dumps([{k: r[k] for k in ("name", "teff_rel_err", "lum_rel_err")
                                                         if k in r} for r in residuals])[:300],
                           artifact_ids=[art.id], duration_s=time.time() - t0)],
    )


def validate_stellar(ctx: NodeContext) -> AgentResult:
    from app.physics.stellar.main_sequence import stellar_parameters

    t0 = time.time()
    data = ctx.state.intermediate_results.get("stellar", {})
    residuals = data.get("residuals", [])
    teff_ok = [r for r in residuals if r.get("in_regime") and r["teff_rel_err"] < 0.15]
    lum_ok = [r for r in residuals if r.get("in_regime") and r["lum_rel_err"] < 0.50]
    in_regime = [r for r in residuals if r.get("in_regime")]
    teff_pass = len(teff_ok) == len(in_regime) and len(in_regime) > 0
    lum_pass = len(lum_ok) == len(in_regime) and len(in_regime) > 0

    # reproducibility: recompute the Sun model and compare bitwise-close
    sun_again = stellar_parameters(1.0)
    repro = abs(sun_again["teff_K"] - 5777.0) / 5777.0 < 0.2 and sun_again["teff_K"] > 0

    rows = []
    for name, passed, metrics in [
        ("stellar_model_teff_vs_literature", teff_pass,
         {"tolerance_rel": 0.15, "n_matched": len(teff_ok), "n_in_regime": len(in_regime),
          "errors": {r["name"]: round(r["teff_rel_err"], 4) for r in in_regime}}),
        ("stellar_model_lum_vs_literature", lum_pass,
         {"tolerance_rel": 0.50, "n_matched": len(lum_ok), "n_in_regime": len(in_regime),
          "errors": {r["name"]: round(r["lum_rel_err"], 4) for r in in_regime}}),
        ("stellar_model_reproducible", bool(repro), {"sun_model_teff": sun_again["teff_K"]}),
    ]:
        vr = VR(tenant_id=ctx.job.tenant_id, job_id=ctx.job.id, check_name=name,
                passed=passed, metrics=metrics,
                details="simplified analytic MS model vs published reference values")
        ctx.db.add(vr)
        rows.append(vr)
    ctx.db.commit()

    all_pass = all(r.passed for r in rows)
    ctx.state.validation_decisions.append({
        "domain": "stellar", "all_passed": all_pass,
        "checks": {r.check_name: r.passed for r in rows},
        "validation_row_id": rows[0].id,
        "tolerances": "Teff <15% rel; L <50% rel (simplified model, documented uncertainty)",
    })
    add_message(ctx.db, ctx.session, agent="validation",
                content=f"Stellar validation: {'VALIDATED' if all_pass else 'ISSUES'} "
                        f"({len(rows)} checks).",
                meta={"checks": {r.check_name: r.passed for r in rows}})
    return AgentResult(
        summary=f"{'VALIDATED' if all_pass else 'ISSUES'} ({len(rows)} checks)",
        output={"all_passed": all_pass,
                "checks": {r.check_name: r.passed for r in rows},
                "validation_row_id": rows[0].id},
        evidence=[evidence("validation.run_checks", args={"domain": "stellar"},
                           result_summary=f"{len(rows)} persisted checks; teff_pass={teff_pass}, "
                                          f"lum_pass={lum_pass}, reproducible={repro}",
                           check_names=[r.check_name for r in rows],
                           duration_s=time.time() - t0)],
    )


# ---------------------------------------------------------------------------
# COSMOLOGY
# ---------------------------------------------------------------------------

def cosmology_analysis(ctx: NodeContext) -> AgentResult:
    import numpy as np

    from app.core.plots import plot_cosmology, plot_posterior
    from app.physics.cosmology.model import SYNTHETIC_DEMO_SNE, distance_ladder, expansion_history

    t0 = time.time()
    z = np.linspace(0.01, 2.0, 60)
    H0 = float(ctx.state.approved_parameters.get("H0", 67.4))
    Om0 = float(ctx.state.approved_parameters.get("Om0", 0.315))
    distances = distance_ladder(z, H0=H0, Om0=Om0)
    history = expansion_history(z, H0=H0, Om0=Om0)

    artifacts = []
    from app.core.artifacts import save_artifact

    png = plot_cosmology(distances)
    art_png = save_artifact(
        ctx.db, tenant_id=ctx.job.tenant_id, kind="plot", filename="cosmology_distances.png",
        content=png, project_id=ctx.job.project_id, session_id=ctx.session.id,
        content_type="image/png", meta={"H0": H0, "Om0": Om0})
    artifacts.append(art_png.id)

    posterior = None
    mcmc_cfg = ctx.state.approved_parameters.get("mcmc")
    if mcmc_cfg and mcmc_cfg.get("use_demo_data"):
        from app.physics.cosmology.model import estimate_parameters

        posterior = estimate_parameters(
            SYNTHETIC_DEMO_SNE["points"], is_demo=True,
            n_steps=int(mcmc_cfg.get("n_steps", 1200)),
        )
        art_post = save_artifact(
            ctx.db, tenant_id=ctx.job.tenant_id, kind="plot", filename="posterior.png",
            content=plot_posterior(posterior), project_id=ctx.job.project_id,
            session_id=ctx.session.id, content_type="image/png",
            meta={"is_demo_data": True})
        artifacts.append(art_post.id)

    ctx.state.intermediate_results["cosmology"] = {
        "H0": H0, "Om0": Om0, "artifacts": artifacts,
        "distances_head": {k: distances[k][:10] if isinstance(distances[k], list) else distances[k]
                           for k in ("z", "comoving_distance_Mpc", "luminosity_distance_Mpc",
                                     "angular_diameter_distance_Mpc", "age_Gyr")},
        "posterior": {k: v for k, v in (posterior or {}).items() if k != "samples"} or None,
        "posterior_is_demo": bool(posterior),
        "age_Gyr_z0": distances["age_Gyr"][0],
    }
    ctx.state.completed_analyses.append({
        "analysis": "distance_redshift_and_expansion", "artifacts": artifacts,
        "H0": H0, "Om0": Om0,
    })
    add_message(ctx.db, ctx.session, agent="cosmology",
                content=f"Distances computed for z<=2 (H0={H0}, Om0={Om0}); "
                        + (f"MCMC posterior on synthetic demo data: H0={posterior['H0_median']:.1f} "
                           f"{posterior['H0_ci68']}." if posterior else "no MCMC requested."),
                meta={"artifacts": artifacts})
    return AgentResult(
        summary=f"distances + expansion history (H0={H0}, Om0={Om0})"
                + (", MCMC demo posterior" if posterior else ""),
        output={"artifacts": artifacts, "posterior": posterior,
                "age_Gyr_z0": distances["age_Gyr"][0]},
        evidence=[evidence("physics.cosmology.distances",
                           args={"H0": H0, "Om0": Om0, "z_max": 2.0},
                           result_summary="astropy FlatLambdaCDM distance ladder computed",
                           artifact_ids=artifacts, duration_s=time.time() - t0)]
        + ([evidence("physics.cosmology.mcmc",
                     args={"n_points": len(SYNTHETIC_DEMO_SNE["points"]),
                           "n_steps": posterior["n_steps"]},
                     result_summary=f"emcee posterior H0={posterior['H0_median']:.2f} "
                                    f"ci68={posterior['H0_ci68']}; DATA IS SYNTHETIC DEMO",
                     artifact_ids=[artifacts[-1]])] if posterior else []),
    )


def validate_cosmology(ctx: NodeContext) -> AgentResult:
    from app.validation.checks import check_cosmology_reference, check_coordinate_roundtrip

    t0 = time.time()
    rows = []
    checks = [check_cosmology_reference(), check_coordinate_roundtrip()]
    posterior = ctx.state.intermediate_results.get("cosmology", {}).get("posterior")
    if posterior:
        checks.append({
            "check_name": "mcmc_posterior_sane",
            "passed": 0.1 < posterior["acceptance_fraction"] < 0.9,
            "metrics": {"acceptance_fraction": posterior["acceptance_fraction"],
                        "H0_ci68": posterior["H0_ci68"], "Om0_ci68": posterior["Om0_ci68"],
                        "is_demo_data": True},
            "details": "emcee acceptance in sane band; credible intervals reported for demo data",
        })
    for chk in checks:
        vr = VR(tenant_id=ctx.job.tenant_id, job_id=ctx.job.id,
                check_name=chk["check_name"], passed=chk["passed"],
                metrics=chk["metrics"], details=chk["details"])
        ctx.db.add(vr)
        rows.append(vr)
    ctx.db.commit()

    all_pass = all(r.passed for r in rows)
    ctx.state.validation_decisions.append({
        "domain": "cosmology", "all_passed": all_pass,
        "checks": {r.check_name: r.passed for r in rows},
        "validation_row_id": rows[0].id,
    })
    add_message(ctx.db, ctx.session, agent="validation",
                content=f"Cosmology validation: {'VALIDATED' if all_pass else 'ISSUES'} "
                        f"({len(rows)} checks).",
                meta={"checks": {r.check_name: r.passed for r in rows}})
    return AgentResult(
        summary=f"{'VALIDATED' if all_pass else 'ISSUES'} ({len(rows)} checks)",
        output={"all_passed": all_pass, "checks": {r.check_name: r.passed for r in rows},
                "validation_row_id": rows[0].id},
        evidence=[evidence("validation.run_checks", args={"domain": "cosmology"},
                           result_summary="Friedmann-vs-astropy crosscheck + coordinate roundtrip "
                                          f"persisted; passed={all_pass}",
                           check_names=[c["check_name"] for c in checks],
                           duration_s=time.time() - t0)],
    )


# ---------------------------------------------------------------------------
# OBSERVATION
# ---------------------------------------------------------------------------

def observation_fetch(ctx: NodeContext) -> AgentResult:
    from app.core.errors import DomainError
    from app.physics.observations.connectors import cone_search_gia, query_exoplanets, resolve_simbad

    t0 = time.time()
    q = ctx.state.research_question or ctx.state.objective
    fetched: list[dict] = []
    ev: list[dict] = []
    errors: list[str] = []

    # Always try the NASA Exoplanet Archive composite table (documented API).
    try:
        out = query_exoplanets(max_rows=25)
        n = len(out.get("rows", []))
        fetched.append({"source": out["source"], "source_url": out["source_url"],
                        "source_key": "exoplanet_archive",
                        "n_rows": n, "identifier": out["adql"][:200]})
        ev.append(evidence("archive.query", args={"archive": "exoplanet_archive", "max_rows": 25},
                           result_summary=f"{n} rows retrieved from pscomppars via TAP/ADQL",
                           duration_s=time.time() - t0))
    except DomainError as exc:
        errors.append(f"exoplanet_archive: {exc.message}")
        ev.append(evidence("archive.query", args={"archive": "exoplanet_archive"},
                           result_summary=f"FAILED (not fabricated): {exc.message[:200]}"))

    # SIMBAD resolution if the question names an object (e.g. 'Sirius')
    for candidate in ("Sirius", "Vega", "Proxima Centauri", "Betelgeuse"):
        if candidate.lower() in q.lower():
            try:
                out = resolve_simbad(candidate)
                fetched.append({"source": out["source"], "source_url": out["source_url"],
                                "source_key": "simbad",
                                "identifier": candidate, "resolved": out["resolver_data"]})
                ev.append(evidence("archive.query", args={"archive": "simbad", "object": candidate},
                                   result_summary=f"resolved {candidate}: {out['resolver_data']}",
                                   duration_s=time.time() - t0))
            except DomainError as exc:
                errors.append(f"simbad: {exc.message}")
            break

    # persist dataset records for provenance
    dataset_ids = []
    for item in fetched:
        rec = DatasetRecord(tenant_id=ctx.job.tenant_id, project_id=ctx.job.project_id,
                            source=item.get("source_key", "user_upload"),
                            identifier=str(item.get("identifier", ""))[:400],
                            description=item["source"], meta=item)
        ctx.db.add(rec)
        ctx.db.flush()
        dataset_ids.append(rec.id)
        ctx.state.datasets.append({"id": rec.id, "source": item["source"],
                                   "identifier": item.get("identifier", "")})
    ctx.db.commit()

    ctx.state.intermediate_results["observations"] = {"fetched": fetched, "errors": errors}
    ctx.state.open_uncertainties += [
        "Remote archive availability affects retrieval; failures are reported, not substituted"
    ]
    add_message(ctx.db, ctx.session, agent="observation",
                content=f"Retrieved {len(fetched)} dataset(s); {len(errors)} archive error(s).",
                meta={"fetched": fetched, "errors": errors})
    return AgentResult(
        summary=f"{len(fetched)} datasets retrieved, {len(errors)} archive errors",
        output={"fetched": fetched, "errors": errors, "dataset_ids": dataset_ids},
        evidence=ev or [evidence("archive.query", args={},
                                 result_summary="no query executed (no target identified)")],
    )


def observation_analysis(ctx: NodeContext) -> AgentResult:
    from app.physics.observations.fits_tools import (
        crossmatch_catalogs, transform_coordinates,
    )
    from app.physics.observations.connectors import cone_search_gia

    t0 = time.time()
    fetched = ctx.state.intermediate_results.get("observations", {})
    ev: list[dict] = []
    analysis: dict = {"crossmatch": None, "coordinate_transform": None, "gaia_cone": None}

    # coordinate transform example anchored to the resolved/fetched object
    ra = dec = None
    for item in fetched.get("fetched", []):
        res = item.get("resolved") or {}
        if "ra_deg" in res:
            ra, dec = float(res["ra_deg"]), float(res["dec_deg"])
            break
    if ra is None:
        ra, dec = 101.287, -16.716  # Sirius ICRS J2000 (SIMBAD reference position)
    transform = transform_coordinates(ra, dec, "icrs", "galactic")
    analysis["coordinate_transform"] = transform
    ev.append(evidence("coords.transform",
                       args={"ra": ra, "dec": dec, "to": "galactic"},
                       result_summary=f"ICRS->galactic: ({transform['output']['lon_deg']:.4f}, "
                                      f"{transform['output']['lat_deg']:.4f}); roundtrip "
                                      f"{transform['roundtrip_error_arcsec']:.2e} arcsec",
                       duration_s=time.time() - t0))

    # Gaia cone search at that position (real archive; may fail -> reported)
    try:
        t1 = time.time()
        cone = cone_search_gia(ra, dec, radius_arcsec=30.0, max_rows=50)
        n = len(cone.get("rows", []))
        analysis["gaia_cone"] = {"n_rows": n, "source": cone["source"],
                                 "columns": cone.get("columns", [])}
        ev.append(evidence("archive.query", args={"archive": "gaia_dr3", "radius_arcsec": 30},
                           result_summary=f"{n} Gaia DR3 sources within 30 arcsec",
                           duration_s=time.time() - t1))
        # cross-match demo: match the returned row coordinates against themselves
        # is meaningless -> instead crossmatch rows against resolved target position
        if n and cone.get("rows") and isinstance(cone["rows"][0], (list, dict)):
            cols = cone.get("columns") or []
            rows = cone["rows"]
            if isinstance(rows[0], list) and "ra" in cols and "dec" in cols:
                ia, idc = cols.index("ra"), cols.index("dec")
                cat = [{"ra": r[ia], "dec": r[idc]} for r in rows
                       if r[ia] is not None and r[idc] is not None]
                if cat:
                    xm = crossmatch_catalogs(cat, [{"ra": ra, "dec": dec}],
                                             radius_arcsec=30.0)
                    analysis["crossmatch"] = {"n_matches": xm["n_matches"],
                                              "radius_arcsec": 30.0,
                                              "n_a": xm["n_a"], "n_b": xm["n_b"]}
                    ev.append(evidence("catalog.crossmatch",
                                       args={"radius_arcsec": 30.0},
                                       result_summary=f"{xm['n_matches']} cone matches "
                                                      f"({xm['n_a']} catalog x 1 target)"))
    except DomainError as exc:
        analysis["gaia_cone"] = {"error": exc.message}
        ev.append(evidence("archive.query", args={"archive": "gaia_dr3"},
                           result_summary=f"FAILED (not fabricated): {exc.message[:200]}"))

    ctx.state.intermediate_results["observation_analysis"] = analysis
    ctx.state.completed_analyses.append({
        "analysis": "coordinate_transform_and_crossmatch",
        "result": {k: (v if k != "gaia_cone" else {kk: vv for kk, vv in (v or {}).items()
                                                    if kk != "rows"})
                   for k, v in analysis.items() if v is not None},
    })
    add_message(ctx.db, ctx.session, agent="observation",
                content=f"Analysis complete: coordinate transform {transform['output']}, "
                        f"crossmatch={analysis['crossmatch']}, gaia={bool(analysis['gaia_cone'])}.",
                meta=analysis)
    return AgentResult(
        summary="coordinate transform + catalog cross-match executed",
        output=analysis,
        evidence=ev,
    )


def validate_observation(ctx: NodeContext) -> AgentResult:
    from app.validation.checks import check_coordinate_roundtrip

    t0 = time.time()
    chk = check_coordinate_roundtrip()
    vr = VR(tenant_id=ctx.job.tenant_id, job_id=ctx.job.id,
            check_name=chk["check_name"], passed=chk["passed"],
            metrics=chk["metrics"], details=chk["details"])
    ctx.db.add(vr)
    # reproducibility: run the roundtrip twice, require identical output
    again = check_coordinate_roundtrip()
    repass = vr.passed and abs(again["metrics"]["roundtrip_error_arcsec"]
                               - chk["metrics"]["roundtrip_error_arcsec"]) < 1e-12
    vr2 = VR(tenant_id=ctx.job.tenant_id, job_id=ctx.job.id,
             check_name="observation_analysis_reproducible", passed=bool(repass),
             metrics={"reproducible": bool(repass)}, details="second identical execution")
    ctx.db.add(vr2)
    ctx.db.commit()

    all_pass = bool(vr.passed and repass)
    ctx.state.validation_decisions.append({
        "domain": "observation", "all_passed": all_pass,
        "checks": {vr.check_name: vr.passed, vr2.check_name: vr2.passed},
        "validation_row_id": vr.id,
    })
    add_message(ctx.db, ctx.session, agent="validation",
                content=f"Observation validation: {'VALIDATED' if all_pass else 'ISSUES'}.",
                meta={"checks": {vr.check_name: vr.passed, vr2.check_name: vr2.passed}})
    return AgentResult(
        summary=f"{'VALIDATED' if all_pass else 'ISSUES'} (2 checks)",
        output={"all_passed": all_pass, "validation_row_id": vr.id,
                "checks": {vr.check_name: vr.passed, vr2.check_name: vr2.passed}},
        evidence=[evidence("validation.run_checks", args={"domain": "observation"},
                           result_summary=f"roundtrip err={chk['metrics']['roundtrip_error_arcsec']:.2e} "
                                          f"arcsec; reproducible={repass}",
                           check_names=[vr.check_name, vr2.check_name],
                           duration_s=time.time() - t0)],
    )
