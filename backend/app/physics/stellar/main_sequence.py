"""Stellar evolution: simplified analytic main-sequence models.

IMPORTANT: these are simplified analytic relations (Salaris & Cassisi 2005,
Ch. 2; Kroupa IMF), NOT MESA-grade evolution tracks. Every output is labeled
with model fidelity so results are never confused with high-fidelity
simulations. Published reference values for well-known stars are included
with literature citations for validation.
"""
import numpy as np

from app.core.errors import ValidationErr

MSUN_L = 3.828e26  # IAU nominal solar luminosity, W
MSUN_R = 6.957e8   # IAU nominal solar radius, m
MSUN_KG = 1.98847e30
SIGMA_SB = 5.670374419e-8
G = 6.67430e-11
MSUN_YR = 3.15576e7

# Main-sequence mass ranges by spectral class (approximate Teff bounds, KM93)
SPECTRAL_BOUNDS = [
    ("O", 30000, 200000),
    ("B", 10000, 30000),
    ("A", 7500, 10000),
    ("F", 6000, 7500),
    ("G", 5200, 6000),
    ("K", 3700, 5200),
    ("M", 2400, 3700),
]


def mass_luminosity(m_msun: float) -> tuple[float, str]:
    """MS mass-luminosity relation with standard piecewise slopes."""
    if not (0.1 < m_msun < 100):
        raise ValidationErr("Main-sequence model valid for 0.1 < M/Msun < 100")
    if m_msun < 0.43:
        return 0.23 * m_msun**2.3, "low-mass branch L ~ M^2.3"
    if m_msun < 2:
        return m_msun**4.0, "solar branch L ~ M^4"
    if m_msun < 55:
        return 1.4 * m_msun**3.5, "intermediate branch L ~ M^3.5"
    return 32000.0 * m_msun, "high-mass branch L ~ M (Eddington)"


def mass_radius(m_msun: float) -> tuple[float, str]:
    """MS mass-radius relation (piecewise)."""
    if not (0.1 < m_msun < 100):
        raise ValidationErr("Main-sequence model valid for 0.1 < M/Msun < 100")
    if m_msun < 1:
        return 0.62 * m_msun**0.8, "R ~ M^0.8 (low mass)"
    if m_msun < 2:
        return m_msun**0.57, "R ~ M^0.57 (solar-like)"
    return 1.26 * m_msun**0.84, "R ~ M^0.84 (high mass)"


def ms_lifetime_yr(m_msun: float, L: float | None = None) -> float:
    """Main-sequence lifetime from the available nuclear energy budget.

    t_MS = eta * M c^2 / L with eta ~= 7.1e-4: the pp-chain converts ~0.7% of
    hydrogen rest mass, and only ~10% of the star's hydrogen burns in the core.
    Mechanically equivalent to the standard 10 Gyr * (M/Msun)^-2.5 scaling near
    solar mass. L is expressed in solar luminosities.
    """
    if L is None:
        L, _ = mass_luminosity(m_msun)
    eta = 7.1e-4
    L_watts = L * MSUN_L
    M_kg = m_msun * MSUN_KG
    return eta * M_kg * (3e8) ** 2 / (L_watts * MSUN_YR)


def teff_from_LR(L_msun: float, R_msun: float) -> float:
    """Stefan-Boltzmann: L = 4 pi R^2 sigma T^4 -> T_eff [K]."""
    if L_msun <= 0 or R_msun <= 0:
        raise ValidationErr("L and R must be positive")
    L = L_msun * MSUN_L
    R = R_msun * MSUN_R
    return (L / (4 * np.pi * R**2 * SIGMA_SB)) ** 0.25


def spectral_class(teff: float) -> tuple[str, int, str]:
    """Classify a main-sequence star by Teff (KM93 main-sequence bands)."""
    for cls, lo, hi in SPECTRAL_BOUNDS:
        if lo <= teff < hi:
            sub = int(np.clip((teff - lo) / (hi - lo) * 10, 0, 9))
            return cls, sub, f"{cls}{sub} (Teff {teff:.0f} K, KM93 main-sequence bounds)"
    return "?", 0, f"Teff {teff:.0f} K outside main-sequence classification range"


def stellar_parameters(m_msun: float) -> dict:
    """Full simplified MS stellar model for a given mass."""
    L, l_branch = mass_luminosity(m_msun)
    R, r_branch = mass_radius(m_msun)
    teff = teff_from_LR(L, R)
    t_ms = ms_lifetime_yr(m_msun, L)
    cls, sub, cls_note = spectral_class(teff)
    remnant = "white dwarf" if m_msun < 8 else ("neutron star" if m_msun < 25 else "black hole")
    return {
        "model_fidelity": "SIMPLIFIED ANALYTIC (not MESA)",
        "assumptions": [
            "Hydrogen main sequence, piecewise mass-luminosity/radius relations",
            "No mass loss, no metallicity dependence, no overshooting",
            "Remnant type from single-star final-mass thresholds (M_ZAMS)",
        ],
        "mass_msun": m_msun,
        "luminosity_msun": L,
        "radius_msun": R,
        "teff_K": teff,
        "spectral_class": f"{cls}{sub}",
        "classification_note": cls_note,
        "ms_lifetime_yr": t_ms,
        "ms_lifetime_Gyr": t_ms / 1e9,
        "expected_remnant": remnant,
        "relations": {"luminosity": l_branch, "radius": r_branch},
        "references": [
            "Salaris & Cassisi 2005, 'Evolution of Stars and Stellar Populations'",
            "Kippenhahn et al. 2012, 'Stellar Structure and Evolution'",
        ],
    }


# Published reference values (literature, with citations) for validation.
REFERENCE_STARS = [
    {"name": "Sun", "mass_msun": 1.0, "teff_K": 5772, "lum_msun": 1.0, "radius_msun": 1.0,
     "source": "IAU nominal solar quantities; Prša et al. 2016"},
    {"name": "Sirius A", "mass_msun": 2.063, "teff_K": 9940, "lum_msun": 25.4, "radius_msun": 1.711,
     "source": "Harper et al. 2017 (van Leeuwen 2007 parallax)"},
    {"name": "Proxima Centauri", "mass_msun": 0.1221, "teff_K": 3042, "lum_msun": 0.00155,
     "radius_msun": 0.1542, "source": "Mann et al. 2015; Kervella et al. 2017"},
    {"name": "Vega", "mass_msun": 2.135, "teff_K": 9602, "lum_msun": 40.12, "radius_msun": 2.362,
     "source": "Yoon et al. 2010; Boyajian et al. 2013"},
    {"name": "Betelgeuse", "mass_msun": 16.5, "teff_K": 3600, "lum_msun": 90000, "radius_msun": 764,
     "source": "Harper et al. 2017 (red supergiant, NOT main sequence)"},
]
