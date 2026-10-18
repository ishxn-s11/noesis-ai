"""Simulation execution service: isolated runs, artifacts, validations.

Executes REBOUND in a subprocess with a hard wall-clock deadline, stores the
trajectory + plots as artifacts, runs Validation checks, and records the
episode in memory — all keyed to tenant/project for provenance.
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.artifacts import save_artifact, save_json_artifact
from app.core.config import settings
from app.core.errors import SimulationErr
from app.core.plots import (
    plot_conservation,
    plot_energy_drift_comparison,
    plot_trajectories_2d,
    plot_trajectories_3d,
)
from app.database.models import Job, ValidationResult
from app.physics.celestial.types import SimulationRequest
from app.validation.checks import run_all_simulation_checks


def run_simulation_job(db: Session, job: Job) -> dict:
    """Job handler: execute a simulation payload, persist evidence, return result.

    Raises on hard failure so the queue can retry / mark failed.
    """
    request = SimulationRequest.model_validate(job.payload.get("request"))
    started = time.time()
    sim_result = execute_isolated(request, timeout_s=job.timeout_s)
    elapsed = time.time() - started

    # --- artifacts: raw result + trajectory/conservation plots ---
    traj_json = save_json_artifact(
        db, tenant_id=job.tenant_id, kind="trajectory",
        filename="trajectories.json", payload=sim_result,
        project_id=job.project_id, session_id=job.session_id,
        meta={"integrator": request.config.integrator, "t_end": request.config.t_end},
    )
    artifacts = [{"id": traj_json.id, "kind": "trajectory", "filename": traj_json.filename}]
    try:
        png2d = save_artifact(
            db, tenant_id=job.tenant_id, kind="plot", filename="trajectories_2d.png",
            content=plot_trajectories_2d(sim_result), project_id=job.project_id,
            session_id=job.session_id, content_type="image/png",
        )
        artifacts.append({"id": png2d.id, "kind": "plot", "filename": png2d.filename})
        png_cons = save_artifact(
            db, tenant_id=job.tenant_id, kind="plot", filename="conservation.png",
            content=plot_conservation(sim_result), project_id=job.project_id,
            session_id=job.session_id, content_type="image/png",
        )
        artifacts.append({"id": png_cons.id, "kind": "plot", "filename": png_cons.filename})
        if request.config.t_end / max(request.config.dt, 1e-12) <= 400:  # short 3D runs
            png3d = save_artifact(
                db, tenant_id=job.tenant_id, kind="plot", filename="trajectories_3d.png",
                content=plot_trajectories_3d(sim_result), project_id=job.project_id,
                session_id=job.session_id, content_type="image/png",
            )
            artifacts.append({"id": png3d.id, "kind": "plot", "filename": png3d.filename})
    except Exception as plot_exc:  # plots must never fail the simulation
        artifacts.append({"kind": "plot_error", "error": str(plot_exc)})

    # --- validation checks, persisted ---
    checks = run_all_simulation_checks(sim_result)
    for chk in checks:
        db.add(ValidationResult(
            tenant_id=job.tenant_id, job_id=job.id, check_name=chk["check_name"],
            passed=chk["passed"], metrics=chk["metrics"], details=chk["details"],
        ))
    db.commit()

    result = {
        "request": json.loads(request.model_dump_json()),
        "status": sim_result["status"],
        "diagnostics": sim_result["diagnostics"],
        "analytics": sim_result["analytics"],
        "meta": {**sim_result["meta"], "executed_in_s": round(elapsed, 3),
                 "executed_by": "REBOUND subprocess with wall-clock deadline"},
        "checks": checks,
        "artifacts": artifacts,
        "snapshots": sim_result["snapshots"],  # for API/frontend rendering
    }
    return result


def execute_isolated(request: SimulationRequest, timeout_s: int | None = None) -> dict:
    """Run the simulation in a child process with a hard deadline."""
    timeout_s = timeout_s or settings.simulation_subprocess_timeout_s
    backend_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="noesis_sim_") as tmp:
        req_path = Path(tmp) / "request.json"
        out_path = Path(tmp) / "result.json"
        req_path.write_text(request.model_dump_json(), encoding="utf-8")
        import os
        env = {"PYTHONPATH": os.pathsep.join([str(backend_root), *sys.path]),
               "PYTHONIOENCODING": "utf-8"}

        proc_env = {**os.environ, **env}
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "app.simulations.subprocess_runner",
                 str(req_path), str(out_path)],
                cwd=str(backend_root), env=proc_env, capture_output=True,
                text=True, timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise SimulationErr(
                f"Simulation exceeded {timeout_s}s wall-clock deadline and was killed"
            ) from exc
        if not out_path.exists():
            raise SimulationErr(
                f"Simulation subprocess produced no output (rc={proc.returncode}): "
                f"{proc.stderr[-800:]}"
            )
        payload = json.loads(out_path.read_text(encoding="utf-8"))
    if not payload.get("ok"):
        raise SimulationErr(payload.get("error", "unknown simulation failure"),
                            details={"traceback": payload.get("traceback", "")[-1200:]})
    return payload["result"]


def save_sweep_plot(db: Session, *, tenant_id: str, project_id: str, session_id: str,
                    labeled_results: list[dict]) -> dict:
    """Plot energy drift across a parameter sweep and persist it."""
    png = plot_energy_drift_comparison(labeled_results)
    art = save_artifact(
        db, tenant_id=tenant_id, kind="plot", filename="sweep_energy_drift.png",
        content=png, project_id=project_id, session_id=session_id, content_type="image/png",
        meta={"n_runs": len(labeled_results)},
    )
    return {"id": art.id, "filename": art.filename}
