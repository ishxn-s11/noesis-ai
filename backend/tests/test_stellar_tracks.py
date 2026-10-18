"""Published PARSEC track integration: interpolation, provenance, honesty.

Physics assertions compare against the observed Sun — a real scientific
correctness check, not a tautology: PARSEC v1.2S at Z=0.014 evaluated at the
solar age must land close to the measured solar parameters.
"""
import pytest

from app.core.errors import ValidationErr
from app.physics.stellar.tracks import (available_metallicities, hr_track,
                                        isochrone, point_parameters,
                                        provenance, track_browser,
                                        track_masses)


def test_grid_covers_documented_range():
    masses = track_masses()
    assert len(masses) == 29
    assert masses[0] == 0.1 and masses[-1] == 100.0


def test_sun_like_star_at_solar_age():
    """1 Msun at 4.6 Gyr must be solar-like (observed: 5772 K, 1.0 Lsun, 1.0 Rsun)."""
    p = point_parameters(1.0, age_yr=4.6e9)
    assert abs(p["teff_K"] - 5772) / 5772 < 0.05      # within 5%
    assert 0.7 < p["luminosity_msun"] < 1.5
    assert 0.85 < p["radius_msun"] < 1.25
    assert p["spectral_class"].startswith("G")


def test_luminosity_increases_with_mass():
    """Mid-MS luminosity must be monotonic in mass across the grid."""
    lums = [point_parameters(m)["luminosity_msun"] for m in (0.2, 0.5, 1.0, 2.0, 10.0, 60.0)]
    assert all(a < b for a, b in zip(lums, lums[1:]))


def test_mass_interpolation_between_grid_tracks():
    """1.7 Msun sits between 1.5 and 2.0 grid tracks; its values must too."""
    lo = point_parameters(1.5)
    hi = point_parameters(2.0)
    mid = point_parameters(1.7)
    assert lo["teff_K"] < mid["teff_K"] < hi["teff_K"]
    assert lo["luminosity_msun"] < mid["luminosity_msun"] < hi["luminosity_msun"]
    assert "bracketing tracks 1.5" in mid["assumptions"][0]


def test_out_of_grid_mass_rejected():
    with pytest.raises(ValidationErr):
        point_parameters(150.0)
    with pytest.raises(ValidationErr):
        point_parameters(0.05)


def test_age_clamping_is_flagged_not_silent():
    p = point_parameters(1.0, age_yr=1e12)
    assert p["age_clamped"] is not None
    assert any("WARNING" in a for a in p["assumptions"])


def test_hr_track_curve_shape():
    tr = hr_track(1.0)
    assert tr["grid_mass_msun"] == 1.0
    assert len(tr["log_teff"]) == len(tr["log_lum"]) > 10
    # hotter start than end for a solar track (ZAMS blue -> giant red)
    assert tr["log_teff"][0] > tr["log_teff"][-1]


def test_provenance_carries_citations_and_grid_info():
    prov = provenance()
    assert "Bressan et al. 2012" in " ".join(prov["citations"])
    assert prov["metallicity_z"] == 0.014
    assert prov["grid"]["n_tracks"] == 29
    assert "philrosenfield.github.io" in prov["source_page"]
    assert "log L = (4.77 - Mbol)" in prov["derived_columns"]["log_lum"]
    # merged multi-metallicity provenance
    assert prov["metallicities_z"] == [0.001, 0.014]
    assert prov["grids"]["0.014"]["helium_y"] == 0.273
    assert prov["grids"]["0.001"]["helium_y"] == 0.25
    assert "log Z" in prov["grid"]["interpolation"]


# --- isochrones -----------------------------------------------------------------

def test_isochrone_sun_age_point():
    """The 4.6 Gyr isochrone must place the 1 Msun point at solar parameters."""
    iso = isochrone(4.6e9)
    pt = next(p for p in iso["points"] if p["mass_msun"] == 1.0)
    teff, lum = 10 ** pt["log_teff"], 10 ** pt["log_lum"]
    assert abs(teff - 5772) / 5772 < 0.05
    assert 0.7 < lum < 1.5


def test_isochrone_ordered_by_mass_and_reports_exclusions():
    """10 Gyr: massive tracks ended — exclusions must be listed, never dropped."""
    iso = isochrone(1e10)
    ms = [p["mass_msun"] for p in iso["points"]]
    assert ms == sorted(ms)                     # ordered by initial mass
    assert len(iso["points"]) + len(iso["excluded_masses_msun"]) == 29
    assert iso["excluded_masses_msun"]          # high-mass tracks end early
    assert 1.0 in ms and 100.0 in iso["excluded_masses_msun"]
    assert "excluded" in iso["derivation"]
    assert "Bressan et al. 2012" in " ".join(iso["provenance"]["citations"])


def test_isochrone_young_age_full_coverage():
    iso = isochrone(1e6)
    assert iso["n_points"] == 29 and iso["excluded_masses_msun"] == []


def test_isochrone_out_of_coverage_rejected_not_silent():
    with pytest.raises(ValidationErr):
        isochrone(1e12)
    with pytest.raises(ValidationErr):
        isochrone(-5.0)


def test_api_isochrone_endpoint(client, tenant_a):
    from tests.conftest import auth

    r = client.get("/api/labs/stellar/isochrone?age_yr=1e9&metallicity_z=0.014",
                   headers=auth(tenant_a["access_token"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["age_yr"] == 1e9
    assert body["n_points"] + len(body["excluded_masses_msun"]) == 29
    assert body["n_points"] > 0
    assert body["derivation"] and body["provenance"]["grid"]["n_tracks"] == 29
    # out-of-coverage age surfaces an explicit error, never an empty curve
    r2 = client.get("/api/labs/stellar/isochrone?age_yr=1e12",
                    headers=auth(tenant_a["access_token"]))
    assert r2.status_code == 422


def test_labeled_distinctly_from_analytic_model():
    from app.physics.stellar.main_sequence import stellar_parameters

    analytic = stellar_parameters(1.0)
    track = point_parameters(1.0)
    assert analytic["model_fidelity"].startswith("SIMPLIFIED ANALYTIC")
    assert track["model_fidelity"].startswith("PUBLISHED TRACK")


def test_api_parsec_source(client, tenant_a):
    """The Stellar Lab endpoint serves track-based results with provenance."""
    from tests.conftest import auth

    r = client.post("/api/labs/stellar",
                    json={"mass_msun": 1.0, "source": "parsec", "age_yr": 4.6e9},
                    headers=auth(tenant_a["access_token"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parameters"]["model_fidelity"].startswith("PUBLISHED TRACK")
    assert body["parameters"]["provenance"]["grid"]["n_tracks"] == 29
    assert "track" in body["parameters"]
    assert body["plot_artifact"]["id"]
    # default remains the analytic model (backward compatible)
    r2 = client.post("/api/labs/stellar", json={"mass_msun": 1.0},
                     headers=auth(tenant_a["access_token"]))
    assert r2.status_code == 200
    assert r2.json()["parameters"]["model_fidelity"].startswith("SIMPLIFIED ANALYTIC")


# --- metallicity grids ----------------------------------------------------------

def test_two_metallicity_grids_available():
    assert available_metallicities() == [0.001, 0.014]
    assert track_masses(0.001) == track_masses(0.014)


def test_metalpoor_grid_matches_official_parsec():
    """Z=0.001, 1 Msun at 4.6 Gyr against the OFFICIAL PARSEC v1.2S CMD
    interface (CMD 3.7, isochrone logAge=9.66, Z=0.001, queried 2026-10-17):
    Mini=1.000 -> Teff=7170 K, logL=0.586, logg=4.23.
    The low-Z tracks really are hot — that is PARSEC v1.2S physics, not a
    conversion bug (verified against stev.oapd.inaf.it)."""
    p = point_parameters(1.0, age_yr=4.6e9, metallicity_z=0.001)
    assert abs(p["teff_K"] - 7170) / 7170 < 0.01
    assert abs(p["luminosity_msun"] / 10 ** 0.586 - 1) < 0.02
    assert abs(p["surface_log_g"] - 4.23) < 0.02


def test_z_interpolation_is_monotonic_and_sandwiched():
    """At fixed mass/age, hotter as Z decreases; interpolated Z strictly
    between the bracketing grid values."""
    age = 4.6e9
    cool = point_parameters(1.0, age_yr=age, metallicity_z=0.014)
    hot = point_parameters(1.0, age_yr=age, metallicity_z=0.001)
    assert hot["teff_K"] > cool["teff_K"]
    for z in (0.002, 0.004, 0.007):
        mid = point_parameters(1.0, age_yr=age, metallicity_z=z)
        assert cool["teff_K"] < mid["teff_K"] < hot["teff_K"]
        assert cool["luminosity_msun"] < mid["luminosity_msun"] < hot["luminosity_msun"]


def test_interpolated_z_is_labeled_not_silent():
    p = point_parameters(1.7, metallicity_z=0.006)
    assert p["metallicity_z"] == 0.006
    assert "Z=0.006" in p["assumptions"][0]
    assert "bracketing tracks 1.5" in p["assumptions"][0]  # mass bracket still reported
    assert any("log Z" in a and "Z=0.001 and Z=0.014" in a for a in p["assumptions"])
    assert p["track"]["metallicity_z"] == 0.006


def test_z_outside_grid_range_rejected_not_extrapolated():
    with pytest.raises(ValidationErr):
        point_parameters(1.0, metallicity_z=0.03)
    with pytest.raises(ValidationErr):
        point_parameters(1.0, metallicity_z=0.0001)


def test_hr_track_carries_z_and_phase_markers():
    tr = hr_track(2.0, metallicity_z=0.001)
    assert tr["metallicity_z"] == 0.001
    assert "Z=0.001" in tr["label"]
    assert tr["ms_end"]["log_lum"] > tr["zams"]["log_lum"]
    assert len(tr["log_teff"]) > 10


def test_track_browser_full_grid():
    b = track_browser(0.004)
    assert b["metallicity_z"] == 0.004
    assert b["metallicities_z"] == [0.001, 0.014]
    assert b["n_tracks"] == len(b["tracks"]) == 29
    assert b["tracks"][0]["grid_mass_msun"] == 0.1
    assert b["tracks"][-1]["grid_mass_msun"] == 100.0
    assert all(len(t["log_teff"]) == len(t["log_lum"]) for t in b["tracks"])
    assert all("ms_end" in t and "zams" in t for t in b["tracks"])
    assert "Bressan et al. 2012" in " ".join(b["provenance"]["citations"])


def test_api_metallicity_param_and_track_browser(client, tenant_a):
    from tests.conftest import auth

    h = auth(tenant_a["access_token"])
    r = client.post("/api/labs/stellar",
                    json={"mass_msun": 1.0, "source": "parsec",
                          "age_yr": 4.6e9, "metallicity_z": 0.004}, headers=h)
    assert r.status_code == 200, r.text
    par = r.json()["parameters"]
    assert "Z=0.004" in par["model_fidelity"]
    assert par["metallicity_z"] == 0.004
    # track browser endpoint serves the full grid with provenance
    r2 = client.get("/api/labs/stellar/tracks", params={"metallicity_z": 0.004},
                    headers=h)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["n_tracks"] == 29
    assert body["metallicities_z"] == [0.001, 0.014]
    assert body["provenance"]["metallicities_z"] == [0.001, 0.014]
    # unauthenticated access is rejected
    assert client.get("/api/labs/stellar/tracks").status_code == 401


def test_track_browser_png_export(client, tenant_a):
    """The track-browser HR diagram exports as a real PNG artifact."""
    from tests.conftest import auth

    h = auth(tenant_a["access_token"])
    r = client.post("/api/labs/stellar/tracks.png",
                    params={"metallicity_z": 0.001}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n_tracks"] == 29 and body["metallicity_z"] == 0.001
    aid = body["plot_artifact"]["id"]
    dl = client.get(f"/api/artifacts/{aid}/download", headers=h)
    assert dl.status_code == 200, dl.text
    assert dl.content[:8] == b"\x89PNG\r\n\x1a\n"  # actual PNG magic, not a stub


def test_apod_normalization_from_cached_payload(monkeypatch):
    """APOD connector normalizes NASA's response (HD links, trimmed copyright)."""
    import json as _json

    from app.physics.observations import connectors

    canned = [{
        "date": "2026-01-02", "title": "Nebula in HD",
        "explanation": "A real captured image.", "media_type": "image",
        "url": "https://apod.nasa.gov/apod/image/x.jpg",
        "hdurl": "https://apod.nasa.gov/apod/image/x_hd.jpg",
        "copyright": "  Photographer  ", "service_version": "v1",
    }]
    monkeypatch.setattr(
        connectors, "_cached_get",
        lambda *a, **k: {"url": "mock", "status_code": 200,
                          "fetched_at": 0.0, "body": _json.dumps(canned)})
    out = connectors.query_apod(count=1)
    assert out["count"] == 1
    item = out["items"][0]
    assert item["hd_url"].endswith("_hd.jpg")
    assert item["copyright"] == "Photographer"
    assert item["media_type"] == "image"
    assert "NASA" in out["source"] and out["source_url"].startswith("https")
    with pytest.raises(ValidationErr):
        connectors.query_apod(count=99)


def test_apod_archive_route(client, tenant_a, monkeypatch):
    import json as _json

    from app.physics.observations import connectors
    from tests.conftest import auth

    monkeypatch.setattr(
        connectors, "_cached_get",
        lambda *a, **k: {"url": "mock", "status_code": 200,
                          "fetched_at": 0.0,
                          "body": _json.dumps([
                              {"date": "2026-03-01", "title": "Comet",
                               "explanation": "x", "media_type": "image",
                               "url": "https://apod.nasa.gov/apod/image/c.jpg"}])})
    r = client.post("/api/labs/archive",
                    json={"archive": "apod", "params": {"count": 1}},
                    headers=auth(tenant_a["access_token"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["archive"] == "apod" and body["items"][0]["title"] == "Comet"
    assert "execution_time_s" in body
    # unknown archives still rejected
    assert client.post("/api/labs/archive",
                       json={"archive": "not_an_archive", "params": {}},
                       headers=auth(tenant_a["access_token"])).status_code == 422


def test_apod_placeholder_falls_back_to_image_library(monkeypatch):
    """When APOD serves NASA-logo placeholders (observed 2026-10), the
    connector transparently switches to NASA's Image and Video Library and
    says so — placeholders are never returned as photographs."""
    import json as _json

    from app.physics.observations import connectors

    placeholder = [{
        "date": "2021-08-21", "title": "NASA Science", "explanation": "",
        "media_type": "image",
        "url": "https://science.nasa.gov/wp-content/themes/nasa-child/"
               "assets/images/nasa-logo@2x.png",
    }]
    search = {"collection": {"items": [{
        "data": [{"nasa_id": "NHQ201708210116",
                   "title": "2017 Total Solar Eclipse",
                   "description": "Total solar eclipse from Oregon.",
                   "date_created": "2017-08-21T18:00:00Z", "center": "HQ"}],
        "links": [{"href": "https://images-assets.nasa.gov/image/"
                            "NHQ201708210116/NHQ201708210116~medium.jpg"}],
    }]}}

    def fake(url, params, **kw):
        # NB: startswith, not `in` — "images-api.nasa.gov" also CONTAINS
        # "api.nasa.gov" as a substring
        body = (_json.dumps(placeholder) if url.startswith("https://api.nasa.gov")
                else _json.dumps(search))
        return {"url": url, "status_code": 200, "fetched_at": 0.0, "body": body}

    monkeypatch.setattr(connectors, "_cached_get", fake)
    out = connectors.query_apod(count=1, q="total solar eclipse")
    assert "Image and Video Library" in out["source"]
    assert "placeholder" in out["note"]
    item = out["items"][0]
    assert item["title"] == "2017 Total Solar Eclipse"
    assert item["hd_url"].endswith("~orig.jpg")          # full-quality link
    assert item["date"] == "2017-08-21"
    assert item["media_type"] == "image"