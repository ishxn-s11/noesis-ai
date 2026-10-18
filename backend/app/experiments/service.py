"""Experiment execution: controlled parameter sweeps over simulation configs.

The Phase-4 demo experiment varies the third body's mass or orbit and reports
stability metrics per run. Every number comes from an actually-executed
REBOUND integration — nothing is interpolated or fabricated.
"""
import json
import time

from sqlalchemy.orm import Session

from app.core.artifacts import save_artifact, save_json_artifact
from app.core.errors import ValidationErr
from app.core.plots import plot_energy_drift_comparison
from app.database.models import Experiment, Job, ValidationResult
from app.physics.celestial.types import SimulationRequest
from app.simulations.service import execute_isolated
from app.validation.checks import run_all_simulation_checks

# Stability proxy thresholds (documented, conservative):
# - inner planet eccentricity proxy < 0.25 over the run
# - planet not ejected (r < 100 AU at all snapshots)
# - system reaches the integration end without ejection
ECC_PROXY_LIMIT = 0.25


def _inner_eccentricity_proxy(run_result: dict, body_name: str) -> float | None:
    """Eccentricity proxy from radial distance extremes: (rmax-rmin)/(rmax+rmin)."""
    body = run_result["snapshots"]["bodies"].get(body_name)
    if not body or len(body["x"]) < 4:
        return None
    import math

    r = [math.sqrt(x * x + y * y + z * z)
         for x, y, z in zip(body["x"], body["y"], body["z"])]
    rmax, rmin = max(r), min(r)
    if rmax + rmin <= 0:
        return None
    return (rmax - rmin) / (rmax + rmin)


def run_experiment_job(db: Session, job: Job) -> dict:
    """Execute a parameter sweep: one isolated REBOUND run per value."""
    payload = job.payload
    exp = db.get(Experiment, payload.get("experiment_id")) if payload.get("experiment_id") else None
    if exp is None:
        raise ValidationErr("experiment_id missing or unknown")
    cfg = exp.config
    sweep_type = cfg.get("sweep_type", "third_body_mass")
    values = cfg.get("values", [])
    if not values:
        raise ValidationErr("Sweep has no values")
    base_request = cfg.get("base_request")
    if not base_request:
        raise ValidationErr("Sweep missing base_request")
    probe_body = cfg.get("probe_body", "inner")  # name key of body whose e-proxy we track
    third_body = cfg.get("third_body", "")

    if exp.status not in {"pending", "running"} and exp.results:
        # Idempotency: already completed — return stored results without rerun.
        return {"experiment_id": exp.id, "results": exp.results,
                "summary": exp.summary, "reused": True}

    exp.status = "running"
    db.commit()

    runs: list[dict] = []
    started = time.time()
    try:
        for value in values:
            request_dict = json.loads(json.dumps(base_request))  # deep copy
            if sweep_type == "third_body_mass":
                _set_third_body_mass(request_dict, third_body, float(value))
                label = f"M₃={value:g} M☉"
            elif sweep_type == "third_body_a":
                _set_third_body_a(request_dict, third_body, float(value))
                label = f"a₃={value:g} AU"
            elif sweep_type == "integrator":
                request_dict["config"]["integrator"] = str(value)
                label = f"{value}"
            else:
                raise ValidationErr(f"Unknown sweep type: {sweep_type}")
            request = SimulationRequest.model_validate(request_dict)
            run_started = time.time()
            try:
                run_result = execute_isolated(request, timeout_s=max(60, job.timeout_s))
                checks = run_all_simulation_checks(run_result)
                for chk in checks:
                    db.add(ValidationResult(
                        tenant_id=job.tenant_id, experiment_id=exp.id, job_id=job.id,
                        check_name=f"{label} :: {chk['check_name']}",
                        passed=chk["passed"], metrics=chk["metrics"], details=chk["details"],
                    ))
                db.commit()
                e_proxy = _inner_eccentricity_proxy(run_result, probe_body)
                stable = (
                    run_result["status"] == "completed"
                    and e_proxy is not None
                    and e_proxy < ECC_PROXY_LIMIT
                )
                runs.append({
                    "label": label,
                    "value": value,
                    "status": run_result["status"],
                    "stable": stable,
                    "ecc_proxy": e_proxy,
                    "energy_drift_rel_max": run_result["diagnostics"]["energy_drift_rel_max"],
                    "angmom_drift_rel_max": run_result["diagnostics"]["angmom_drift_rel_max"],
                    "min_pairwise_distance_au": run_result["diagnostics"]["min_pairwise_distance_au"],
                    "checks": [{"name": c["check_name"], "passed": c["passed"]} for c in checks],
                    "meta": run_result["meta"],
                    "wall_time_s": round(time.time() - run_started, 3),
                    "label_only_full_result_saved": False,
                })
                # keep only the first run's full snapshot payload (size control)
                if runs and "full_result" not in runs[0]:
                    runs[0]["full_result"] = run_result
            except Exception as run_exc:  # record failures as evidence, keep sweeping
                runs.append({"label": label, "value": value, "status": "error",
                             "stable": False, "error": str(run_exc)})
                db.add(ValidationResult(
                    tenant_id=job.tenant_id, experiment_id=exp.id, job_id=job.id,
                    check_name=f"{label} :: execution",
                    passed=False, metrics={}, details=str(run_exc),
                ))
                db.commit()
    finally:
        # persist progress for resume/observability
        exp.results = [{k: v for k, v in r.items() if k != "full_result"} for r in runs]
        db.commit()

    completed = [r for r in runs if r.get("status") not in {"error"}]
    stable_count = sum(1 for r in runs if r.get("stable"))
    summary = {
        "sweep_type": sweep_type,
        "n_runs": len(runs),
        "n_executed": len(completed),
        "n_stable": stable_count,
        "stability_fraction": stable_count / len(runs) if runs else 0.0,
        "stability_criteria": {
            "ecc_proxy_limit": ECC_PROXY_LIMIT,
            "definition": "stable = integration completed AND (rmax-rmin)/(rmax+rmin) of probe body < limit",
        },
        "total_wall_time_s": round(time.time() - started, 2),
        "all_checks_passed": all(
            c["passed"] for r in runs for c in r.get("checks", [])
        ) if runs else False,
    }

    # artifacts: results JSON + drift comparison plot
    results_art = save_json_artifact(
        db, tenant_id=job.tenant_id, kind="table", filename="sweep_results.json",
        payload={"summary": summary, "runs": [{k: v for k, v in r.items() if k != "full_result"}
                                              for r in runs]},
        project_id=job.project_id, session_id=job.session_id, meta=summary,
    )
    plotted = [{"label": r.get("label", ""),
                "diagnostics": {"energy_drift_rel_max": r.get("energy_drift_rel_max", 0.0)}}
               for r in runs if r.get("energy_drift_rel_max") is not None]
    plot_art = None
    if plotted:
        try:
            png = plot_energy_drift_comparison(plotted)
            plot_art = save_artifact(
                db, tenant_id=job.tenant_id, kind="plot", filename="sweep_energy_drift.png",
                content=png, project_id=job.project_id, session_id=job.session_id,
                content_type="image/png", meta={"n_runs": len(plotted)},
            )
        except Exception as plot_exc:
            import logging

            logging.getLogger("noesis.experiments").warning(
                "sweep drift plot failed: %s", plot_exc, exc_info=True)
            plot_art = None

    # Persist the FIRST run's full trajectory (positions + diagnostics) so the
    # frontend can render real integrated orbits from a sweep.
    traj_art = None
    png2d = None
    first_full = runs[0].get("full_result") if runs else None
    if first_full:
        try:
            traj_art = save_json_artifact(
                db, tenant_id=job.tenant_id, kind="trajectory",
                filename="sweep_first_run_trajectories.json",
                payload=first_full, project_id=job.project_id,
                session_id=job.session_id,
                meta={"label": runs[0].get("label", ""),
                      "integrator": first_full.get("meta", {}).get("integrator")},
            )
            from app.core.plots import plot_trajectories_2d

            png2d = save_artifact(
                db, tenant_id=job.tenant_id, kind="plot",
                filename="sweep_first_run_trajectories.png",
                content=plot_trajectories_2d(first_full),
                project_id=job.project_id, session_id=job.session_id,
                content_type="image/png",
                meta={"label": runs[0].get("label", "")},
            )
        except Exception as plot_exc:
            import logging

            logging.getLogger("noesis.experiments").warning(
                "sweep trajectory plot failed: %s", plot_exc, exc_info=True)
            traj_art = None
            png2d = None

    exp.status = "completed"
    exp.results = [{k: v for k, v in r.items() if k != "full_result"} for r in runs]
    exp.summary = summary
    db.commit()

    return {
        "experiment_id": exp.id,
        "summary": summary,
        "runs": exp.results,
        "artifacts": [{"id": results_art.id, "filename": results_art.filename, "kind": "table"}]
        + ([{"id": plot_art.id, "filename": plot_art.filename, "kind": "plot"}] if plot_art else [])
        + ([{"id": traj_art.id, "filename": traj_art.filename, "kind": "trajectory"}]
           if traj_art else [])
        + ([{"id": png2d.id, "filename": png2d.filename, "kind": "plot"}]
           if png2d else []),
        "full_first_run": runs[0].get("full_result") if runs else None,
    }


def _set_third_body_mass(request_dict: dict, third_body: str, mass_msun: float) -> None:
    if mass_msun <= 0:
        raise ValidationErr("Third body mass must be positive")
    for body in request_dict["bodies"]:
        if body["name"] == third_body:
            body["mass_value"] = mass_msun
            body["mass_unit"] = "msun"
            return
    raise ValidationErr(f"Third body '{third_body}' not in base_request")


def _set_third_body_a(request_dict: dict, third_body: str, a_au: float) -> None:
    if a_au <= 0:
        raise ValidationErr("Third body semi-major axis must be positive")
    for body in request_dict["bodies"]:
        if body["name"] == third_body:
            body["a"] = a_au
            return
    raise ValidationErr(f"Third body '{third_body}' not in base_request")
