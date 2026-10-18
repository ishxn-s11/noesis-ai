"""Analytical Keplerian mechanics used for validation of numerical results.

All formulas are standard textbook results (e.g., Murray & Dermott 1999);
constants follow IAU nominal values via CODATA/IAU 2015.
"""
import math

from astropy import constants as const
from astropy import units as u

G_SI = const.G.si.value  # m^3 kg^-1 s^-2
MSUN = const.M_sun.si.value
AU = const.au.si.value
YEAR = 3.15576e7  # Julian year, IAU-defined (365.25 days), seconds


def orbital_period_s(m_total_kg: float, a_m: float) -> float:
    """Kepler's third law: P = 2*pi*sqrt(a^3 / (G*M))."""
    return 2.0 * math.pi * math.sqrt(a_m**3 / (G_SI * m_total_kg))


def orbital_period_yr(m_total_msun: float, a_au: float) -> float:
    """P in years for solar-mass/AU inputs (P^2 = a^3/M with a[AU], M[Msun])."""
    return math.sqrt(a_au**3 / m_total_msun)


def circular_velocity_ms(a_m: float, mCentral_kg: float) -> float:
    """v_circ = sqrt(G M / a)."""
    return math.sqrt(G_SI * mCentral_kg / a_m)


def specific_orbital_energy(a_m: float, m_total_kg: float) -> float:
    """epsilon = -G M / (2a) [J/kg]."""
    return -G_SI * m_total_kg / (2.0 * a_m)


def hill_sphere_radius(a_au: float, m_planet_msun: float, m_star_msun: float) -> float:
    """r_H = a * (m_p / (3 M))^(1/3) [au]."""
    return a_au * (m_planet_msun / (3.0 * m_star_msun)) ** (1.0 / 3.0)


def roche_limit_density(radius_m: float, density_kg_m3: float) -> float:
    """Fluid Roche limit: a_R = 2.44 * R_primary * (rho_primary/rho_sat)^(1/3)."""
    return 2.44 * radius_m


def escape_velocity_ms(m_kg: float, r_m: float) -> float:
    return math.sqrt(2.0 * G_SI * m_kg / r_m)


def au_to_m(x: float) -> float:
    return (x * u.AU).to(u.m).value


def yr_to_s(x: float) -> float:
    return (x * u.yr).to(u.s).value
