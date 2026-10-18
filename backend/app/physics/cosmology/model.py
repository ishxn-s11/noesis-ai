"""ΛCDM cosmology: Friedmann expansion, distances, parameter inference.

Uses astropy.cosmology for validated computations. Parameter estimation runs
emcee against user-supplied data points; the bundled example dataset is
explicitly labeled SYNTHETIC DEMO DATA and never presented as observations.
"""
import numpy as np
from astropy import units as u
from astropy.cosmology import FlatLambdaCDM, Planck18

from app.core.errors import ValidationErr


def make_cosmology(H0: float = 67.4, Om0: float = 0.315, Tcmb0: float = 2.725) -> FlatLambdaCDM:
    if H0 <= 0 or not (0 < Om0 <= 1.5):
        raise ValidationErr("Invalid cosmological parameters: require H0>0, 0<Om0<=1.5")
    return FlatLambdaCDM(H0=H0 * u.km / u.s / u.Mpc, Om0=Om0, Tcmb0=Tcmb0 * u.K)


def expansion_history(z: np.ndarray, H0: float, Om0: float) -> dict:
    """E(z) = H(z)/H0 for flat ΛCDM: sqrt(Om(1+z)^3 + Ol)."""
    z = np.asarray(z, dtype=float)
    Ol = 1.0 - Om0
    Ez = np.sqrt(Om0 * (1 + z) ** 3 + Ol)
    Hz = H0 * Ez
    return {"z": z.tolist(), "Ez": Ez.tolist(), "Hz_km_s_Mpc": Hz.tolist()}


def distance_ladder(z: np.ndarray, H0: float = 67.4, Om0: float = 0.315) -> dict:
    """Comoving, luminosity and angular-diameter distances vs redshift."""
    cosmo = make_cosmology(H0, Om0)
    z_arr = np.atleast_1d(np.asarray(z, dtype=float))
    if np.any(z_arr < 0) or np.any(z_arr > 20):
        raise ValidationErr("Redshifts must satisfy 0 <= z <= 20")
    dc = cosmo.comoving_distance(z_arr).to(u.Mpc).value
    dl = cosmo.luminosity_distance(z_arr).to(u.Mpc).value
    da = cosmo.angular_diameter_distance(z_arr).to(u.Mpc).value
    age = cosmo.age(z_arr).to(u.Gyr).value
    return {
        "z": z_arr.tolist(),
        "comoving_distance_Mpc": dc.tolist(),
        "luminosity_distance_Mpc": dl.tolist(),
        "angular_diameter_distance_Mpc": da.tolist(),
        "age_Gyr": age.tolist(),
        "H0_km_s_Mpc": H0,
        "Om0": Om0,
        "Ol0": 1 - Om0,
        "reference": "astropy.cosmology.FlatLambdaCDM (FlatLCDM, curvature=0)",
    }


def friedmann_check(z: float, H0: float, Om0: float) -> dict:
    """Show the Friedmann equation terms at a redshift for teaching/validation."""
    Ol0 = 1 - Om0
    matter = Om0 * (1 + z) ** 3
    dark_energy = Ol0
    radiation_term = 4.1e-5 * (1 + z) ** 4  # Omega_r approx for Tcmb=2.725K, photons only
    total = matter + dark_energy + radiation_term
    return {
        "z": z,
        "Omega_m_z": matter,
        "Omega_Lambda": dark_energy,
        "Omega_r_z_approx": radiation_term,
        "E_z": total ** 0.5,
        "H_z_km_s_Mpc": H0 * total ** 0.5,
        "equation": "(H/H0)^2 = Om(1+z)^3 + Or(1+z)^4 + Ol",
    }


# ---------------------------------------------------------------------------
# Parameter estimation (emcee) against user-supplied distance moduli
# ---------------------------------------------------------------------------

SYNTHETIC_DEMO_SNE = {
    "label": "SYNTHETIC DEMO DATA - generated from Planck18 with noise; NOT real observations",
    "is_demo": True,
    "points": [
        # (z, mu, sigma_mu) drawn from Planck18 + 0.15 mag scatter, fixed seed
    ],
}


def _demo_sne() -> list[list[float]]:
    rng = np.random.default_rng(42)
    zs = np.array([0.07, 0.12, 0.18, 0.24, 0.31, 0.38, 0.45, 0.55, 0.65, 0.78, 0.9, 1.05, 1.2, 1.35])
    mu_true = Planck18.distmod(zs).value
    mu_obs = mu_true + rng.normal(0, 0.15, size=len(zs))
    return [[float(z), float(m), 0.15] for z, m in zip(zs, mu_obs)]


SYNTHETIC_DEMO_SNE["points"] = _demo_sne()


def _log_likelihood(theta, z, mu, sigma):
    H0, Om0 = theta
    if not (50 < H0 < 100) or not (0.05 < Om0 < 0.7):
        return -np.inf
    cosmo = FlatLambdaCDM(H0=H0 * u.km / u.s / u.Mpc, Om0=Om0)
    model = cosmo.distmod(z).to(u.mag).value
    return -0.5 * np.sum(((mu - model) / sigma) ** 2 + np.log(2 * np.pi * sigma**2))


def estimate_parameters(
    points: list[list[float]],
    *,
    is_demo: bool,
    n_steps: int = 2000,
    burn_in: int = 500,
    seed: int = 0,
) -> dict:
    """MCMC posterior for (H0, Om0) from (z, mu, sigma_mu) data points.

    Data provenance MUST be declared by the caller; demo data is generated
    from Planck18 and labeled as such — it is never treated as observations.
    """
    import emcee

    if len(points) < 4:
        raise ValidationErr("Need at least 4 (z, mu, sigma) points for parameter estimation")
    arr = np.asarray(points, dtype=float)
    z, mu, sigma = arr[:, 0], arr[:, 1], np.clip(arr[:, 2], 1e-3, None)

    def log_prob(theta):
        ll = _log_likelihood(theta, z, mu, sigma)
        return ll if np.isfinite(ll) else -np.inf

    rng = np.random.default_rng(seed)
    p0 = np.array([[rng.uniform(65, 75), rng.uniform(0.25, 0.38)] for _ in range(16)])
    sampler = emcee.EnsembleSampler(16, 2, log_prob)
    sampler.run_mcmc(p0, n_steps, progress=False)
    chain = sampler.get_chain(discard=burn_in, thin=10, flat=True)
    H0_samples, Om0_samples = chain[:, 0], chain[:, 1]
    return {
        "is_demo_data": is_demo,
        "data_provenance": "SYNTHETIC DEMO (Planck18-generated)" if is_demo else "user-supplied",
        "n_points": len(points),
        "n_steps": n_steps,
        "burn_in": burn_in,
        "priors": "H0 ~ U(50,100) km/s/Mpc, Om0 ~ U(0.05,0.7)",
        "H0_median": float(np.median(H0_samples)),
        "H0_ci68": [float(np.percentile(H0_samples, 16)), float(np.percentile(H0_samples, 84))],
        "Om0_median": float(np.median(Om0_samples)),
        "Om0_ci68": [float(np.percentile(Om0_samples, 16)), float(np.percentile(Om0_samples, 84))],
        "acceptance_fraction": float(np.mean(sampler.acceptance_fraction)),
        "samples": [
            [float(h), float(o)] for h, o in zip(H0_samples[:: max(1, len(H0_samples)//2000)],
                                                 Om0_samples[:: max(1, len(Om0_samples)//2000)])
        ],
    }
