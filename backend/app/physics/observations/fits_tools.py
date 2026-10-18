"""FITS inspection, coordinate transforms, light curves, cross-matching."""
import io

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy import units as u
from astropy.time import Time

from app.core.errors import ValidationErr


def inspect_fits(content: bytes, *, max_hdu: int = 10) -> dict:
    """Inspect a FITS file: HDUs, headers, image statistics, table preview."""
    try:
        with fits.open(io.BytesIO(content)) as hdul:
            hdus = []
            for idx, hdu in enumerate(hdul[:max_hdu]):
                header = {k: _jsonable(v) for k, v in hdu.header.items() if k}
                info: dict = {"index": idx, "type": type(hdu).__name__, "header": header}
                if hdu.data is not None:
                    data = np.asarray(hdu.data)
                    info["shape"] = list(data.shape)
                    if np.issubdtype(data.dtype, np.number) and data.size:
                        finite = data[np.isfinite(data)]
                        info["stats"] = {
                            "min": float(np.min(finite)) if finite.size else None,
                            "max": float(np.max(finite)) if finite.size else None,
                            "mean": float(np.mean(finite)) if finite.size else None,
                            "std": float(np.std(finite)) if finite.size else None,
                        }
                    if getattr(hdu, "columns", None):
                        info["columns"] = [c.name for c in hdu.columns]
                        info["n_rows"] = len(hdu.data)
                hdus.append(info)
            return {"valid_fits": True, "n_hdus": len(hdul), "hdus": hdus}
    except Exception as exc:
        raise ValidationErr(f"Invalid FITS file: {exc}") from exc


def _jsonable(value):
    try:
        if isinstance(value, (int, float, str, bool)) or value is None:
            return value
        return str(value)
    except Exception:
        return str(value)


def transform_coordinates(
    ra_deg: float, dec_deg: float, frame_from: str = "icrs", frame_to: str = "galactic",
    equinox_from: str = "J2000", obstime: str | None = None,
) -> dict:
    """Coordinate transformation via astropy.coordinates (with round-trip error)."""
    coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame=frame_from,
                     equinox=equinox_from, obstime=obstime)
    try:
        target = getattr(coord, frame_to)
    except AttributeError as exc:
        raise ValidationErr(f"Unknown target frame: {frame_to}") from exc
    back = getattr(target, frame_from)
    roundtrip_arcsec = coord.separation(back).arcsec
    return {
        "input": {"frame": frame_from, "ra_deg": ra_deg, "dec_deg": dec_deg},
        "output": {"frame": frame_to,
                   "lon_deg": float(target.spherical.lon.deg),
                   "lat_deg": float(target.spherical.lat.deg)},
        "roundtrip_error_arcsec": roundtrip_arcsec,
        "library": "astropy.coordinates.SkyCoord",
    }


def light_curve_stats(times: list[float], mags: list[float], t_format: str = "jd") -> dict:
    """Basic photometric time-series analysis: stats, phase folding, periodogram."""
    from scipy.signal import lombscargle

    t = np.asarray(times, dtype=float)
    m = np.asarray(mags, dtype=float)
    if len(t) < 8 or len(t) != len(m):
        raise ValidationErr("Need >= 8 (time, magnitude) pairs")
    order = np.argsort(t)
    t, m = t[order], m[order]
    t_norm = t - t[0]
    # Lomb-Scargle periodogram: scipy expects ANGULAR frequencies (rad/day)
    freqs_cyc = np.linspace(1.0 / (t_norm[-1] / 3.0), 1.0 / 0.05, 4000)
    if np.any(freqs_cyc <= 0):
        raise ValidationErr("Time baseline too short for period search")
    freqs = 2 * np.pi * freqs_cyc
    power = lombscargle(t_norm, m - m.mean(), freqs, normalize=True)
    best = int(np.argmax(power))
    period = 2 * np.pi / freqs[best]
    return {
        "n_points": len(t),
        "time_format": t_format,
        "t_span_days": float(t_norm[-1]),
        "mag_mean": float(m.mean()),
        "mag_std": float(m.std()),
        "mag_min": float(m.min()),
        "mag_max": float(m.max()),
        "best_period_days": float(period),
        "periodogram_power_max": float(power[best]),
        "method": "Lomb-Scargle (scipy.signal.lombscargle), normalized",
        "caution": "Automated period detection; verify with folding/phase plots",
    }


def crossmatch_catalogs(
    cat_a: list[dict], cat_b: list[dict], radius_arcsec: float = 2.0,
    ra_key: str = "ra", dec_key: str = "dec",
) -> dict:
    """Cone-search cross-match of two catalogs using astropy SkyCoord."""
    if not cat_a or not cat_b:
        raise ValidationErr("Both catalogs must be non-empty")
    try:
        coords_a = SkyCoord([c[ra_key] for c in cat_a] * u.deg,
                            [c[dec_key] for c in cat_a] * u.deg)
        coords_b = SkyCoord([c[ra_key] for c in cat_b] * u.deg,
                            [c[dec_key] for c in cat_b] * u.deg)
    except KeyError as exc:
        raise ValidationErr(f"Missing coordinate key {exc}") from exc
    idx_a, idx_b, sep, _ = coords_a.search_around_sky(coords_b, radius_arcsec * u.arcsec)
    matches = [
        {"a_index": int(ia), "b_index": int(ib), "separation_arcsec": float(s.arcsec)}
        for ia, ib, s in zip(idx_a, idx_b, sep)
    ]
    return {
        "n_a": len(cat_a), "n_b": len(cat_b),
        "radius_arcsec": radius_arcsec, "n_matches": len(matches),
        "matches": matches[:500], "method": "astropy SkyCoord.search_around_sky",
    }


def heliocentric_correction(ra_deg: float, dec_deg: float, jd: float) -> dict:
    """Barycentric/Heliocentric time conversion example via astropy.time."""
    t = Time(jd, format="jd", scale="utc")
    light_travel = t.light_travel_time(SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg))
    t_hjd = t + light_travel
    return {
        "input_jd": jd, "hjd": float(t_hjd.jd), "light_travel_time_s": float(light_travel.sec),
        "method": "astropy.time.Time.light_travel_time (heliocentric)",
    }
