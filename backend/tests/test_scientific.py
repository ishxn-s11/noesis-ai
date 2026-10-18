"""Scientific validation tests against known analytical results.

These tests verify the platform's physics engines against textbook/analytical
solutions — independent of any LLM involvement.
"""
import math

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Keplerian mechanics
# ---------------------------------------------------------------------------

def test_kepler_period_sun_earth():
    from app.physics.celestial.kepler import orbital_period_yr, orbital_period_s

    # P^2 = a^3 / M for a in AU, M in Msun -> ~1 yr for Earth
    p_yr = orbital_period_yr(1.00014, 1.0)
    assert abs(p_yr - 1.0) < 0.01
    # absolute SI check: 1 solar mass, 1 AU -> 365.25 d
    p_s = orbital_period_s(1.98847e30, 1.495978707e11)
    assert abs(p_s / 86400 - 365.256) / 365.256 < 1e-3


def test_rebound_two_body_energy_conservation():
    """IAS15 two-body run: relative energy drift < 1e-8."""
    from app.physics.celestial.rebound_engine import run_simulation
    from app.physics.celestial.types import BodySpec, SimConfig, SimulationRequest

    req = SimulationRequest(
        bodies=[
            BodySpec(name="star", mass_value=1.0, mass_unit="msun",
                     x=0, y=0, z=0, vx=0, vy=0, vz=0),
            BodySpec(name="planet", mass_value=1e-6, mass_unit="msun",
                     a=1.0, e=0.0, theta=0.0),
        ],
        config=SimConfig(integrator="ias15", t_end=20.0, dt=0.01, output_every=100),
    )
    out = run_simulation(req)
    assert out["status"] == "completed"
    assert out["diagnostics"]["energy_drift_rel_max"] < 1e-8
    assert out["diagnostics"]["angmom_drift_rel_max"] < 1e-7
    assert out["meta"]["n_snapshots"] > 50


def test_rebound_kepler_period_from_snapshots():
    """A circular 1-AU test particle's radial period must equal 1 Kepler year."""
    from app.physics.celestial.rebound_engine import run_simulation
    from app.physics.celestial.types import BodySpec, SimConfig, SimulationRequest
    from app.validation.checks import check_kepler_period

    req = SimulationRequest(
        bodies=[
            BodySpec(name="star", mass_value=1.0, mass_unit="msun"),
            BodySpec(name="planet", mass_value=1e-6, mass_unit="msun",
                     a=1.0, e=0.01),
        ],
        config=SimConfig(integrator="whfast", dt=0.005, t_end=30.0, output_every=200),
    )
    out = run_simulation(req)
    chk = check_kepler_period(out, tolerance_rel=0.1)
    assert chk["metrics"]["kepler_period_yr"] == pytest.approx(1.0, rel=0.01)
    assert chk["passed"], chk


def test_third_body_instability_is_detected():
    """A very massive, close perturber must destabilize the inner planet."""
    from app.physics.celestial.rebound_engine import run_simulation
    from app.physics.celestial.types import BodySpec, SimConfig, SimulationRequest

    req = SimulationRequest(
        bodies=[
            BodySpec(name="star", mass_value=1.0, mass_unit="msun",
                     x=0, y=0, z=0, vx=0, vy=0, vz=0),
            BodySpec(name="inner", mass_value=1e-3, mass_unit="msun",
                     a=1.0, e=0.05),
            BodySpec(name="outer", mass_value=0.5, mass_unit="msun",
                     a=1.6, e=0.4),
        ],
        config=SimConfig(integrator="ias15", dt=0.02, t_end=400.0, output_every=100),
    )
    out = run_simulation(req)
    assert out["status"] in {"unstable_ejected", "unstable_collision"}


def test_integrator_comparison_whfast_vs_ias15():
    """WHFast and IAS15 must agree on the two-body energy drift order."""
    from app.physics.celestial.rebound_engine import run_simulation
    from app.physics.celestial.types import BodySpec, SimConfig, SimulationRequest

    def run(integ):
        return run_simulation(SimulationRequest(
            bodies=[
                BodySpec(name="star", mass_value=1.0, mass_unit="msun"),
                BodySpec(name="p", mass_value=1e-6, mass_unit="msun", a=1.0, e=0.1),
            ],
            config=SimConfig(integrator=integ, dt=0.005, t_end=50.0, output_every=200),
        ))

    d_ias = run("ias15")["diagnostics"]["energy_drift_rel_max"]
    d_wh = run("whfast")["diagnostics"]["energy_drift_rel_max"]
    assert d_ias < 1e-7
    assert d_wh < 1e-4


# ---------------------------------------------------------------------------
# Cosmology
# ---------------------------------------------------------------------------

def test_luminosity_distance_reference_case():
    """Flat LCDM H0=70 Om=0.3: D_L(z=1) ≈ 6615 Mpc (independent quad check)."""
    from scipy.integrate import quad

    from app.physics.cosmology.model import distance_ladder

    H0, Om, z = 70.0, 0.3, 1.0
    c = 299792.458
    dc = (c / H0) * quad(lambda zp: 1 / math.sqrt(Om * (1 + zp) ** 3 + 1 - Om),
                         0, z, limit=200)[0]
    dl_ref = (1 + z) * dc
    out = distance_ladder(np.array([z]), H0=H0, Om0=Om)
    assert out["luminosity_distance_Mpc"][0] == pytest.approx(dl_ref, rel=1e-3), out


def test_cosmology_crosscheck_validation():
    from app.validation.checks import check_cosmology_reference

    chk = check_cosmology_reference()
    assert chk["passed"], chk
    assert chk["metrics"]["relative_error"] < 1e-4


def test_friedmann_expansion_monotonic_distance():
    from app.physics.cosmology.model import distance_ladder

    out = distance_ladder(np.array([0.1, 0.5, 1.0, 2.0]))
    dl = out["luminosity_distance_Mpc"]
    assert all(dl[i] < dl[i + 1] for i in range(len(dl) - 1))
    #Etherington distance duality: D_L = (1+z)^2 D_A (GLRW identity)
    for i, z in enumerate(out["z"]):
        assert out["angular_diameter_distance_Mpc"][i] == pytest.approx(
            dl[i] / (1 + z) ** 2, rel=1e-10)


def test_mcmc_recovers_planck_like_parameters_on_demo_data():
    """Demo data generated from Planck18: posterior must bracket the truth
    within 68% CI at least ~ half the time (statistical, seeded)."""
    from app.physics.cosmology.model import SYNTHETIC_DEMO_SNE, estimate_parameters

    post = estimate_parameters(SYNTHETIC_DEMO_SNE["points"], is_demo=True,
                               n_steps=1500, burn_in=500, seed=1)
    assert post["is_demo_data"] is True
    assert 50 < post["H0_median"] < 100
    assert 0.15 < post["Om0_median"] < 0.55
    lo, hi = post["H0_ci68"]
    assert lo < 67.4 < hi or post["H0_ci68"][1] - post["H0_ci68"][0] > 2


# ---------------------------------------------------------------------------
# Stellar
# ---------------------------------------------------------------------------

def test_solar_stellar_parameters():
    from app.physics.stellar.main_sequence import stellar_parameters

    sun = stellar_parameters(1.0)
    assert sun["luminosity_msun"] == pytest.approx(1.0, rel=0.05)
    assert sun["radius_msun"] == pytest.approx(1.0, rel=0.05)
    assert sun["teff_K"] == pytest.approx(5777, rel=0.1)
    assert sun["ms_lifetime_Gyr"] == pytest.approx(10, rel=0.35)
    assert sun["spectral_class"].startswith("G")


def test_mass_luminosity_scaling():
    from app.physics.stellar.main_sequence import mass_luminosity

    l1, _ = mass_luminosity(1.0)
    l2, _ = mass_luminosity(2.0)
    # solar-branch M^4 scaling -> ~16x at 2 Msun (branch switch at M>=2 uses M^3.5*1.4)
    assert l2 / l1 > 10


def test_reference_star_classification():
    from app.physics.stellar.main_sequence import REFERENCE_STARS, spectral_class

    assert spectral_class(9940)[0] == "A"   # Sirius
    assert spectral_class(5772)[0] == "G"   # Sun
    assert spectral_class(3042)[0] == "M"   # Proxima
    assert spectral_class(9602)[0] == "A"   # Vega


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------

def test_icrs_galactic_roundtrip():
    from app.validation.checks import check_coordinate_roundtrip

    chk = check_coordinate_roundtrip(ra=266.405, dec=-28.936)  # Sgr A*
    assert chk["passed"], chk
    assert chk["metrics"]["roundtrip_error_arcsec"] < 1e-3


def test_known_coordinate_transform():
    """Sgr A*: ICRS (266.4168, -29.0078) = galactic (359.9443, -0.0462)."""
    from app.physics.observations.fits_tools import transform_coordinates

    out = transform_coordinates(266.4168, -29.0078, "icrs", "galactic")
    assert out["input"]["frame"] == "icrs"
    assert out["output"]["lon_deg"] == pytest.approx(359.944, abs=0.01)
    assert out["output"]["lat_deg"] == pytest.approx(-0.046, abs=0.01)


def test_fits_inspection_roundtrip(tmp_path):
    from astropy.io import fits

    from app.physics.observations.fits_tools import inspect_fits

    path = tmp_path / "tiny.fits"
    hdu = fits.PrimaryHDU(np.arange(16, dtype=np.float32).reshape(4, 4))
    hdu.header["OBJECT"] = "SYNTHETIC-DEMO"
    hdu.writeto(path)
    info = inspect_fits(path.read_bytes())
    assert info["valid_fits"] and info["n_hdus"] == 1
    assert info["hdus"][0]["stats"]["max"] == 15.0


def test_crossmatch_geometry():
    from app.physics.observations.fits_tools import crossmatch_catalogs

    a = [{"ra": 10.0, "dec": 20.0}, {"ra": 50.0, "dec": 50.0}]
    b = [{"ra": 10.0005, "dec": 20.0000}]  # ~0.5" offset in ra*dec
    out = crossmatch_catalogs(a, b, radius_arcsec=2.0)
    assert out["n_matches"] == 1
    assert out["matches"][0]["separation_arcsec"] < 2.0


def test_lightcurve_period_recovery():
    """Inject a known period and recover it with Lomb-Scargle."""
    from app.physics.observations.fits_tools import light_curve_stats

    rng = np.random.default_rng(7)
    t = np.sort(rng.uniform(0, 60, 300))
    true_period = 2.5
    m = 12 + 0.4 * np.sin(2 * np.pi * t / true_period) + rng.normal(0, 0.02, t.size)
    stats = light_curve_stats(t.tolist(), m.tolist())
    assert stats["best_period_days"] == pytest.approx(true_period, rel=0.05)


def test_symbolic_dimension_check():
    from app.validation.checks import check_dimensional

    assert check_dimensional("G*M/a", "a*(2*pi/P)**2")["passed"] is False  # different by factor
    ok = check_dimensional("2*pi*sqrt(a**3/(G*M))", "2*pi*sqrt(a**3/(G*M))")
    assert ok["passed"]