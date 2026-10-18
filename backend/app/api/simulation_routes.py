"""Simulation, experiment, and physics-laboratory endpoints."""
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.service import CurrentUser, get_current_user
from app.core.artifacts import artifact_public, save_artifact
from app.core.errors import NotFoundErr, ValidationErr
from app.database.models import Artifact, Experiment, Job, ValidationResult
from app.database.session import get_db, set_tenant
from app.physics.celestial.types import SimulationRequest
from app.simulations import queue

router = APIRouter(tags=["simulations"])


def _db(raw_db: Session, user: CurrentUser) -> Session:
    set_tenant(raw_db, user.tenant_id)
    return raw_db


class SimulationIn(BaseModel):
    request: SimulationRequest
    project_id: str = ""
    session_id: str = ""


@router.post("/simulations", summary="Queue an isolated N-body simulation")
def start_simulation(body: SimulationIn, user: CurrentUser = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> dict:
    db = _db(db, user)
    job = queue.enqueue(
        db, tenant_id=user.tenant_id, kind="simulation",
        payload={"request": body.request.model_dump()},
        project_id=body.project_id, session_id=body.session_id,
        timeout_s=300, max_attempts=2,
    )
    return {"job_id": job.id, "status": job.status}


@router.get("/simulations/{job_id}/result", summary="Simulation result snapshot+diagnostics")
def simulation_result(job_id: str, user: CurrentUser = Depends(get_current_user),
                      db: Session = Depends(get_db)) -> dict:
    db = _db(db, user)
    job = db.query(Job).filter(Job.id == job_id, Job.tenant_id == user.tenant_id).first()
    if not job:
        raise NotFoundErr("Job not found")
    if job.status not in {"succeeded", "failed"}:
        return {"status": job.status, "result": None}
    return {"status": job.status, "error": job.error, "result": job.result}


@router.get("/simulations/{job_id}/result.png", summary="Trajectory plot PNG")
def simulation_plot(job_id: str, user: CurrentUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    from fastapi.responses import Response

    db = _db(db, user)
    job = db.query(Job).filter(Job.id == job_id, Job.tenant_id == user.tenant_id).first()
    if not job or job.status != "succeeded":
        raise NotFoundErr("Simulation plot not available yet")
    from app.core.plots import plot_trajectories_2d

    png = plot_trajectories_2d(job.result)
    return Response(content=png, media_type="image/png")


# --- experiments (parameter sweeps) -------------------------------------------

class ExperimentIn(BaseModel):
    project_id: str
    session_id: str = ""
    name: str = Field(min_length=3, max_length=300)
    objective: str = ""
    sweep_type: str = Field(pattern="^(third_body_mass|third_body_a|integrator)$")
    values: list = Field(min_length=2, max_length=50)
    base_request: dict
    third_body: str = ""
    probe_body: str = "inner"


@router.post("/experiments", summary="Create + queue a parameter-sweep experiment")
def start_experiment(body: ExperimentIn, user: CurrentUser = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> dict:
    db = _db(db, user)
    exp = Experiment(
        tenant_id=user.tenant_id, project_id=body.project_id,
        session_id=body.session_id, name=body.name, objective=body.objective,
        config={"sweep_type": body.sweep_type, "values": body.values,
                "base_request": body.base_request, "third_body": body.third_body,
                "probe_body": body.probe_body},
        status="pending",
    )
    db.add(exp)
    db.commit()
    # validate base_request early so the user gets a 422 instead of a failed job
    try:
        SimulationRequest.model_validate(body.base_request)
    except Exception as exc:
        exp.status = "failed"
        db.commit()
        raise ValidationErr(f"Invalid base_request: {exc}") from exc
    job = queue.enqueue(db, tenant_id=user.tenant_id, kind="experiment",
                        payload={"experiment_id": exp.id},
                        project_id=body.project_id, session_id=body.session_id,
                        timeout_s=1200, max_attempts=2)
    exp.job_id = job.id
    db.commit()
    return {"experiment_id": exp.id, "job_id": job.id, "status": job.status}


@router.get("/experiments/{experiment_id}", summary="Experiment results + validations")
def get_experiment(experiment_id: str, user: CurrentUser = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    db = _db(db, user)
    exp = db.query(Experiment).filter(
        Experiment.id == experiment_id, Experiment.tenant_id == user.tenant_id
    ).first()
    if not exp:
        raise NotFoundErr("Experiment not found")
    validations = db.query(ValidationResult).filter(
        ValidationResult.experiment_id == experiment_id
    ).order_by(ValidationResult.created_at).all()
    return {
        "id": exp.id, "name": exp.name, "objective": exp.objective, "status": exp.status,
        "config": {k: v for k, v in exp.config.items() if k != "base_request"},
        "results": exp.results, "summary": exp.summary, "job_id": exp.job_id,
        "created_at": exp.created_at.isoformat(),
        "validations": [{"check_name": v.check_name, "passed": v.passed,
                         "metrics": v.metrics, "details": v.details}
                        for v in validations],
    }


@router.get("/experiments", summary="List experiments")
def list_experiments(project_id: str | None = None,
                     user: CurrentUser = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> list[dict]:
    db = _db(db, user)
    rows = db.query(Experiment).filter(Experiment.tenant_id == user.tenant_id)
    if project_id:
        rows = rows.filter(Experiment.project_id == project_id)
    out = []
    for e in rows.order_by(Experiment.created_at.desc()).limit(100).all():
        out.append({"id": e.id, "name": e.name, "status": e.status,
                    "sweep_type": e.config.get("sweep_type"),
                    "summary": e.summary, "created_at": e.created_at.isoformat(),
                    "project_id": e.project_id, "session_id": e.session_id})
    return out


# --- labs: stellar / cosmology / observations ----------------------------------

class StellarIn(BaseModel):
    mass_msun: float = Field(gt=0.05, lt=120)
    # "analytic" = simplified MS relations; "parsec" = published PARSEC
    # v1.2S evolution tracks (bundled, locally interpolated, with provenance)
    source: Literal["analytic", "parsec"] = "analytic"
    age_yr: float | None = Field(default=None, gt=0, description=
        "parsec only: evaluate at this age (defaults to mid-MS age)")
    metallicity_z: float | None = Field(default=None, gt=0, lt=1, description=
        "parsec only: metallicity; available grids Z=0.001 and Z=0.014, "
        "interpolated in log Z in between (default 0.014)")


@router.post("/labs/stellar", summary="Stellar model + HR artifact (analytic or PARSEC tracks)")
def stellar_lab(body: StellarIn, user: CurrentUser = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
    from app.core.plots import plot_hr_diagram
    from app.physics.stellar.main_sequence import (REFERENCE_STARS,
                                                   stellar_parameters)

    db = _db(db, user)
    tracks = None
    if body.source == "parsec":
        from app.physics.stellar.tracks import (DEFAULT_Z, available_metallicities,
                                                point_parameters)

        z = body.metallicity_z if body.metallicity_z is not None else DEFAULT_Z
        params = point_parameters(body.mass_msun, age_yr=body.age_yr,
                                  metallicity_z=z)
        tracks = [params["track"]]
        filename = f"hr_{body.mass_msun:g}msun_parsec_z{z:g}.png"
        title = (f"HR diagram — PARSEC v1.2S track for {body.mass_msun:g} M☉ "
                 f"(Z={z:g}, Bressan et al. 2012)")
        meta_z = {"metallicity_z": z, "metallicities_z": available_metallicities()}
    else:
        params = stellar_parameters(body.mass_msun)
        filename = f"hr_{body.mass_msun:g}msun.png"
        title = "Hertzsprung–Russell diagram (simplified analytic models)"
        meta_z = {}
    hr_png = plot_hr_diagram([params], REFERENCE_STARS, tracks=tracks, title=title)
    art = save_artifact(db, tenant_id=user.tenant_id, kind="plot",
                        filename=filename, content=hr_png,
                        content_type="image/png",
                        meta={"mass_msun": body.mass_msun, "source": body.source,
                              **meta_z})
    return {"parameters": params, "plot_artifact": artifact_public(art),
            "reference_stars": REFERENCE_STARS}


@router.get("/labs/stellar/tracks",
            summary="Full-grid PARSEC evolutionary paths (track browser)")
def stellar_tracks(metallicity_z: float = Query(default=0.014,
                                                description="grid or interpolated Z"),
                   user: CurrentUser = Depends(get_current_user)) -> dict:
    from app.physics.stellar.tracks import track_browser

    return track_browser(metallicity_z)


@router.get("/labs/stellar/isochrone",
            summary="Fixed-age isochrone derived from the PARSEC track grid")
def stellar_isochrone(age_yr: float = Query(...,
                                            description="isochrone age in years"),
                      metallicity_z: float = Query(default=0.014,
                                                    description="grid or interpolated Z"),
                      user: CurrentUser = Depends(get_current_user)) -> dict:
    from app.physics.stellar.tracks import isochrone

    return isochrone(age_yr, metallicity_z)


@router.post("/labs/stellar/tracks.png",
             summary="Full-grid HR diagram PNG artifact (track-browser export)")
def stellar_tracks_png(metallicity_z: float = Query(default=0.014),
                       user: CurrentUser = Depends(get_current_user),
                       db: Session = Depends(get_db)) -> dict:
    from app.core.plots import plot_track_grid
    from app.physics.stellar.main_sequence import REFERENCE_STARS
    from app.physics.stellar.tracks import track_browser

    db = _db(db, user)
    b = track_browser(metallicity_z)
    png = plot_track_grid(b["tracks"], REFERENCE_STARS, metallicity_z=metallicity_z)
    art = save_artifact(db, tenant_id=user.tenant_id, kind="plot",
                        filename=f"hr_tracks_z{metallicity_z:g}.png", content=png,
                        content_type="image/png",
                        meta={"metallicity_z": metallicity_z, "n_tracks": b["n_tracks"]})
    return {"plot_artifact": artifact_public(art), "n_tracks": b["n_tracks"],
            "metallicity_z": metallicity_z}


class CosmologyIn(BaseModel):
    z_max: float = Field(default=2.0, gt=0.001, le=20)
    H0: float = Field(default=67.4, gt=20, lt=120)
    Om0: float = Field(default=0.315, gt=0.01, lt=0.99)
    n_redshift: int = Field(default=80, ge=4, le=500)


@router.post("/labs/cosmology", summary="Distance ladder + expansion history")
def cosmology_lab(body: CosmologyIn, user: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict:
    import numpy as np

    from app.core.plots import plot_cosmology
    from app.physics.cosmology.model import distance_ladder, expansion_history, friedmann_check

    db = _db(db, user)
    z = np.linspace(0.001, body.z_max, body.n_redshift)
    distances = distance_ladder(z, H0=body.H0, Om0=body.Om0)
    history = expansion_history(z, H0=body.H0, Om0=body.Om0)
    fried = friedmann_check(float(body.z_max), body.H0, body.Om0)
    png = plot_cosmology(distances)
    art = save_artifact(db, tenant_id=user.tenant_id, kind="plot",
                        filename="cosmology_distances.png", content=png,
                        content_type="image/png",
                        meta={"H0": body.H0, "Om0": body.Om0})
    return {"distances": distances, "expansion": history, "friedmann": fried,
            "plot_artifact": artifact_public(art)}


class MCMCIn(BaseModel):
    use_demo_data: bool = True
    n_steps: int = Field(default=1500, ge=400, le=8000)
    data_points: list[list[float]] | None = None


@router.post("/labs/cosmology/mcmc", summary="H0/Om0 posterior (emcee UQ)")
def cosmology_mcmc(body: MCMCIn, user: CurrentUser = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    from app.core.errors import ValidationErr as VE
    from app.core.plots import plot_posterior
    from app.physics.cosmology.model import SYNTHETIC_DEMO_SNE, estimate_parameters

    db = _db(db, user)
    if body.use_demo_data or body.data_points is None:
        points, is_demo = SYNTHETIC_DEMO_SNE["points"], True
    else:
        points, is_demo = body.data_points, False
    result = estimate_parameters(points, is_demo=is_demo, n_steps=body.n_steps)
    png = plot_posterior(result)
    art = save_artifact(db, tenant_id=user.tenant_id, kind="plot",
                        filename="mcmc_posterior.png", content=png,
                        content_type="image/png",
                        meta={"is_demo_data": is_demo, "n_steps": body.n_steps})
    return {"posterior": result, "plot_artifact": artifact_public(art),
            "data_notice": SYNTHETIC_DEMO_SNE["label"] if is_demo
            else "user-supplied data; provenance is caller's responsibility"}


@router.post("/labs/fits", summary="Inspect an uploaded FITS file")
async def fits_lab(file: UploadFile = File(...),
                   user: CurrentUser = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    from app.physics.observations.fits_tools import inspect_fits

    db = _db(db, user)
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise ValidationErr("FITS file too large (50 MB limit)")
    info = inspect_fits(content)
    art = save_artifact(db, tenant_id=user.tenant_id, kind="fits",
                        filename=file.filename or "upload.fits", content=content,
                        content_type=file.content_type or "application/octet-stream",
                        meta={"n_hdus": info.get("n_hdus")})
    return {"inspection": info, "artifact_id": art.id}


class ArchiveQueryIn(BaseModel):
    archive: str = Field(pattern="^(exoplanet_archive|gaia|vizier|simbad|arxiv|apod)$")
    params: dict = Field(default_factory=dict)


@router.post("/labs/archive", summary="Query a documented public archive API")
def archive_query(body: ArchiveQueryIn, user: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict:
    import time

    from app.physics.observations.connectors import (
        cone_search_gia, query_apod, query_exoplanets, query_vizier, resolve_simbad,
        search_arxiv,
    )

    db = _db(db, user)
    t0 = time.time()
    p = body.params
    if body.archive == "exoplanet_archive":
        out = query_exoplanets(where=p.get("where", "defaultflag=1"),
                               max_rows=int(p.get("max_rows", 100)))
    elif body.archive == "gaia":
        out = cone_search_gia(float(p["ra_deg"]), float(p["dec_deg"]),
                              radius_arcsec=float(p.get("radius_arcsec", 30)),
                              max_rows=int(p.get("max_rows", 100)))
    elif body.archive == "vizier":
        out = query_vizier(p["catalog"], p.get("constraint", ""),
                           max_rows=int(p.get("max_rows", 100)))
    elif body.archive == "simbad":
        out = resolve_simbad(p["object_name"])
    elif body.archive == "apod":
        out = query_apod(count=int(p.get("count", 12)), q=p.get("q"))
    else:
        out = search_arxiv(p.get("query", ""), int(p.get("max_results", 5)))
    # strip the raw body blob for TAP responses to keep payloads bounded
    out.pop("body", None)
    if "rows" in out and len(out["rows"]) > 500:
        out["rows"] = out["rows"][:500]
    return {**out, "execution_time_s": round(time.time() - t0, 3)}


class TransformIn(BaseModel):
    ra: float = Field(ge=0, le=360)
    dec: float = Field(ge=-90, le=90)
    to: str = "galactic"
    from_frame: str = "icrs"


@router.post("/labs/transform", summary="ICRS/Galactic coordinate transform + round-trip")
def transform(body: TransformIn, user: CurrentUser = Depends(get_current_user),
              db: Session = Depends(get_db)) -> dict:
    from app.physics.observations.fits_tools import transform_coordinates

    db = _db(db, user)
    return transform_coordinates(body.ra, body.dec, body.from_frame, body.to)


class CrossmatchIn(BaseModel):
    catalog_a: list[dict]
    catalog_b: list[dict]
    radius_arcsec: float = Field(default=2.0, gt=0.001, le=600)


@router.post("/labs/crossmatch", summary="Cone cross-match two catalogs")
def crossmatch(body: CrossmatchIn, user: CurrentUser = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict:
    from app.physics.observations.fits_tools import crossmatch_catalogs

    db = _db(db, user)
    return crossmatch_catalogs(body.catalog_a, body.catalog_b,
                               radius_arcsec=body.radius_arcsec)


class LightCurveIn(BaseModel):
    times: list[float] = Field(min_length=8, max_length=50000)
    mags: list[float] = Field(min_length=8, max_length=50000)


@router.post("/labs/lightcurve", summary="Photometric time-series stats + periodogram")
def lightcurve(body: LightCurveIn, user: CurrentUser = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict:
    from app.physics.observations.fits_tools import light_curve_stats

    db = _db(db, user)
    if len(body.times) != len(body.mags):
        raise ValidationErr("times and mags must have equal length")
    return light_curve_stats(body.times, body.mags)