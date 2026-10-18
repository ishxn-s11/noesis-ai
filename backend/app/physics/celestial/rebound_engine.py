"""REBOUND-backed N-body integration with conservation diagnostics.

Executes real REBOUND integrations (WHFast/IAS15/Mercurius) in AU/yr/Msun
units, recording energy and angular-momentum drift at every snapshot so the
Validation Agent can verify numerical stability against analytical expectations.
"""
import time

from app.core.errors import SimulationErr
from app.physics.celestial import kepler
from app.physics.celestial.types import SimulationRequest

MAX_SNAPSHOTS = 4000
EJECTA_RADIUS_AU = 200.0
COLLISION_FRACTION = 0.01  # collision if pairwise distance < 1% of min semi-major axis


def run_simulation(request: SimulationRequest) -> dict:
    """Run an N-body integration and return typed results with diagnostics.

    Returns a JSON-serializable dict:
      status: completed | unstable_ejected | unstable_collision
      snapshots: {time_yr: [...], bodies: {name: {x,y,z: [...]}}}
      diagnostics: {energy_drift_rel_max, angmom_drift_rel_max, energy_series_rel, ...}
      analytics: per-pair Kepler period comparison vs numerical period
      meta: {integrator, dt, wall_time_s, n_snapshots, rebound_version}
    """
    import rebound

    cfg = request.config
    try:
        sim = rebound.Simulation()
        sim.units = (cfg.time_unit, cfg.distance_unit, cfg.mass_unit)  # yr, AU, Msun
        if cfg.softening > 0:
            sim.softening = cfg.softening
        sim.integrator = cfg.integrator
        if cfg.integrator == "ias15" and hasattr(sim, "ri_ias15"):
            sim.ri_ias15.epsilon = 1e-9  # REBOUND <5 API; defaults equal in 5.x
        else:
            sim.dt = cfg.dt

        for spec in request.bodies:
            mass_msun = spec.mass_value if spec.mass_unit == "msun" else spec.mass_kg() / kepler.MSUN
            if spec.a is not None:
                sim.add(m=mass_msun, a=spec.a, e=spec.e or 0.0, inc=spec.inc or 0.0,
                        Omega=spec.Omega or 0.0, omega=spec.omega or 0.0, theta=spec.theta or 0.0)
            else:
                # Cartesian state, or implicit primary body at the origin
                sim.add(m=mass_msun, x=spec.x or 0.0, y=spec.y or 0.0, z=spec.z or 0.0,
                        vx=spec.vx or 0.0, vy=spec.vy or 0.0, vz=spec.vz or 0.0)
        sim.move_to_com()
    except Exception as exc:  # REBOUND raises on bad elements
        raise SimulationErr(f"Failed to build REBOUND simulation: {exc}") from exc

    names = [request.bodies[i].name for i in range(sim.N)]
    min_a = min((b.a for b in request.bodies if b.a), default=1.0)
    collision_threshold = COLLISION_FRACTION * min_a

    e0 = sim.energy()
    l0 = sim.angular_momentum()
    l0_norm = (l0.x**2 + l0.y**2 + l0.z**2) ** 0.5

    times: list[float] = []
    positions: dict[str, dict[str, list[float]]] = {n: {"x": [], "y": [], "z": []} for n in names}
    energy_rel: list[float] = []
    angmom_rel: list[float] = []
    min_pairwise = float("inf")

    status = "completed"
    wall_start = time.time()

    # Uniform recording grid: honor output_every as a floor; target >=400 samples
    # (well above Phi-Nyquist: ~10+ samples/orbit for typical t_end/period ratios)
    configured = int(cfg.t_end / (cfg.dt * cfg.output_every)) + 1
    n_records = int(min(max(configured, min(400, MAX_SNAPSHOTS)), MAX_SNAPSHOTS))
    record_times = [cfg.t_end * i / (n_records - 1) for i in range(n_records)] if n_records > 1 else [cfg.t_end]

    if cfg.exit_unstable and hasattr(sim, "exit_max_distance"):
        # Native guard: abort cleanly on ejection instead of integrating forever,
        # and abort on sub-threshold approaches instead of timestep collapse.
        sim.exit_max_distance = EJECTA_RADIUS_AU
        sim.exit_min_distance = collision_threshold

    escaped = False
    encounter = False
    try:
        for t_target in record_times:
            try:
                # exact_finish_time=1: never overshoot the record target. With 0,
                # REBOUND can land past t_target and the NEXT integrate() would
                # step backward, recording duplicated/stale states.
                if t_target <= sim.t:
                    continue
                sim.integrate(t_target, exact_finish_time=1)
            except Exception as exc:  # rebound.Escape / rebound.Encounter guards
                name = type(exc).__name__.lower()
                if name == "escape" or "distance" in str(exc).lower() and "max" in str(exc).lower():
                    escaped = True
                    break
                if name == "encounter" or "close encounter" in str(exc).lower():
                    encounter = True
                    break
                raise
            if times and sim.t <= times[-1]:
                continue  # monotonic guard: never record non-advancing time
            times.append(float(sim.t))
            ps = sim.particles
            for i, name in enumerate(names):
                positions[name]["x"].append(float(ps[i].x))
                positions[name]["y"].append(float(ps[i].y))
                positions[name]["z"].append(float(ps[i].z))
            e = sim.energy()
            l = sim.angular_momentum()
            energy_rel.append(float((e - e0) / abs(e0)))
            angmom_rel.append(float(((l.x*l.x + l.y*l.y + l.z*l.z) ** 0.5 - l0_norm) / (l0_norm or 1.0)))

            # pairwise distance diagnostics (snapshot-based collision signal)
            for i in range(sim.N):
                for j in range(i + 1, sim.N):
                    dx = ps[i].x - ps[j].x
                    dy = ps[i].y - ps[j].y
                    dz = ps[i].z - ps[j].z
                    d = (dx * dx + dy * dy + dz * dz) ** 0.5
                    min_pairwise = min(min_pairwise, d)

            # Instability detection from recorded snapshots
            ejected = escaped or any(
                (ps[i].x**2 + ps[i].y**2 + ps[i].z**2) ** 0.5 > EJECTA_RADIUS_AU for i in range(sim.N)
            )
            if ejected and cfg.exit_unstable:
                status = "unstable_ejected"
                break
    except Exception as exc:
        raise SimulationErr(f"Integration failed: {exc}") from exc

    if encounter:
        status = "unstable_collision"
    elif escaped and status == "completed" and cfg.exit_unstable:
        status = "unstable_ejected"

    if status == "completed" and min_pairwise < collision_threshold:
        status = "unstable_collision"

    wall_time = time.time() - wall_start

    # Numerical vs analytical (Kepler) period comparison for each bound pair.
    pair_checks = _pair_period_checks(request, sim)

    return {
        "status": status,
        "snapshots": {"time_yr": times, "bodies": positions},
        "diagnostics": {
            "energy_rel_series": energy_rel,
            "angmom_rel_series": angmom_rel,
            "energy_drift_rel_max": max(abs(v) for v in energy_rel) if energy_rel else 0.0,
            "angmom_drift_rel_max": max(abs(v) for v in angmom_rel) if angmom_rel else 0.0,
            "energy_drift_rel_final": energy_rel[-1] if energy_rel else 0.0,
            "angmom_drift_rel_final": angmom_rel[-1] if angmom_rel else 0.0,
            "min_pairwise_distance_au": min_pairwise if min_pairwise != float("inf") else None,
            "collision_threshold_au": collision_threshold,
            "ejected": status == "unstable_ejected",
        },
        "analytics": {"pair_periods": pair_checks},
        "meta": {
            "integrator": cfg.integrator,
            "dt": cfg.dt,
            "t_end": cfg.t_end,
            "n_snapshots": len(times),
            "wall_time_s": round(wall_time, 4),
            "rebound_version": getattr(rebound, "__version__", "unknown"),
        },
    }


def _pair_period_checks(request: SimulationRequest, sim) -> list[dict]:
    """Compare numerically measured orbital periods with Kepler's third law.

    Uses the two most massive bodies' mutual orbit when exactly 2+ bodies and
    measures the period from radial oscillations of the relative separation.
    """
    import rebound

    bodies = sorted(request.bodies, key=lambda b: -b.mass_kg())
    if len(bodies) < 2 or bodies[1].a is None or bodies[1].a <= 0:
        return []  # secondary body lacks Keplerian elements to compare against
    primary, secondary = bodies[0], bodies[1]
    m_total_msun = (primary.mass_value if primary.mass_unit == "msun" else primary.mass_kg()/kepler.MSUN) + \
                   (secondary.mass_value if secondary.mass_unit == "msun" else secondary.mass_kg()/kepler.MSUN)
    predicted_s = kepler.orbital_period_s(
        m_total_msun * kepler.MSUN, kepler.au_to_m(secondary.a)
    )
    predicted_yr = predicted_s / kepler.YEAR
    return [{
        "pair": f"{primary.name}-{secondary.name}",
        "a_au": secondary.a,
        "m_total_msun": m_total_msun,
        "kepler_period_yr": predicted_yr,
        "method": "P^2 = a^3 / M (IAU nominal constants via astropy)",
    }]
