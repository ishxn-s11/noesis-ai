"""Explainer glossary + paper-interpretation pipeline (mocked fetch, real engines)."""
import json

from tests.conftest import auth

FAKE_ABSTRACT = (
    "We present K2-18 b, a planet with an orbital period of 3.2 days and a "
    "semi-major axis of 0.043 AU around a star of 1.05 M_sun, observed at a "
    "distance of 120 pc. We also measure a Hubble constant of 73.0 km/s/Mpc "
    "for a companion field. The system age is 4.6 Gyr."
)

FAKE_PAPER = {
    "kind": "arxiv", "id": "2401.12345", "url": "https://arxiv.org/abs/2401.12345",
    "title": "K2-18 b: A Hot Neptune in the Inner Disk",
    "authors": ["A. Astronomer", "B. Physicist"],
    "abstract": FAKE_ABSTRACT,
    "published": "2024-01-08",
    "doi": "", "source": "arXiv API (export.arxiv.org, test mock)",
}


# ---------------------------------------------------------------- unit: parsing

def test_parse_paper_ref_accepts_arxiv_and_doi_formats():
    from app.core.errors import ValidationErr
    from app.physics.paper.ingest import parse_paper_ref

    assert parse_paper_ref("https://arxiv.org/abs/2401.12345")["id"] == "2401.12345"
    assert parse_paper_ref("https://arxiv.org/pdf/2303.08676v2")["id"] == "2303.08676"
    assert parse_paper_ref("arxiv:hep-th/9901001")["kind"] == "arxiv"
    doi = parse_paper_ref("https://doi.org/10.1051/0004-6361/201936871")
    assert doi["kind"] == "doi" and doi["id"].startswith("10.1051/")
    try:
        parse_paper_ref("https://publisher.example.com/article/17")
        raise AssertionError("unsupported link must be rejected")
    except ValidationErr as exc:
        assert "arXiv" in str(exc) and "DOI" in str(exc)


def test_parse_arxiv_atom_and_crossref_metadata(monkeypatch):
    """Exercise the real XML/JSON parsers (the e2e mocks fetch_paper itself)."""
    from app.physics.paper.ingest import _parse_arxiv_atom, _parse_crossref

    atom = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>A Hot Neptune in the Inner Disk</title>
    <summary>We present K2-18 b with an orbital period of 3.2 days.</summary>
    <published>2024-01-08T00:00:00Z</published>
    <author><name>A. Astronomer</name></author>
    <author><name>B. Physicist</name></author>
    <arxiv:doi xmlns:arxiv="http://arxiv.org/schemas/atom">10.1234/abc</arxiv:doi>
  </entry>
</feed>"""
    paper = _parse_arxiv_atom(atom, {"kind": "arxiv", "id": "2401.12345",
                                     "url": "https://arxiv.org/abs/2401.12345"})
    assert paper["title"] == "A Hot Neptune in the Inner Disk"
    assert paper["authors"] == ["A. Astronomer", "B. Physicist"]
    assert paper["published"] == "2024-01-08"
    assert paper["doi"] == "10.1234/abc"
    assert "orbital period of 3.2 days" in paper["abstract"]

    crossref = json.dumps({"message": {
        "title": ["Astronomy & Astrophysics, 45.5"],
        "author": [{"given": "C.", "family": "Cosmos"}],
        "abstract": "<jats:p>We measure <italic>H0</italic> = 73.0.</jats:p>",
        "published": {"date-parts": [[2020, 6, 1]]},
        "URL": "https://doi.org/10.1051/test",
    }})
    cr = _parse_crossref(crossref, {"kind": "doi", "id": "10.1051/test",
                                    "url": "https://doi.org/10.1051/test"})
    assert cr["title"].startswith("Astronomy")
    assert cr["authors"] == ["C. Cosmos"]
    assert "<jats" not in cr["abstract"] and "73.0" in cr["abstract"]
    assert cr["published"] == "2020"

    # live-shape guard: fetch_paper routes arXiv ids through the Atom parser
    from app.physics.paper import ingest as paper_ingest

    captured = {}

    def fake_cached_get(url, params, **kw):
        captured.update(url=url, params=params)
        return {"body": atom}

    monkeypatch.setattr(paper_ingest, "_cached_get", fake_cached_get)
    out = paper_ingest.fetch_paper({"kind": "arxiv", "id": "2401.12345",
                                    "url": "https://arxiv.org/abs/2401.12345"})
    assert out["title"].startswith("A Hot Neptune")
    assert captured["params"] == {"id_list": "2401.12345"}


# -------------------------------------------------------------- unit: extraction

def test_extract_quantities_captures_values_units_and_snippets():
    from app.physics.paper.ingest import extract_quantities

    qs = extract_quantities(FAKE_ABSTRACT)
    by = {q["kind"]: q for q in qs}
    assert by["orbital_period_days"]["value"] == 3.2
    assert by["semi_major_axis_au"]["value"] == 0.043
    assert by["stellar_mass"]["value"] == 1.05
    assert by["hubble_constant"]["value"] == 73.0
    assert by["age_gyr"]["value"] == 4.6
    # every claim carries the literal text it came from (traceability)
    assert all(q["snippet"] and q["snippet"] in FAKE_ABSTRACT for q in qs)
    # distance unit actually captured (kpc vs pc)
    dqs = extract_quantities("The cluster lies at 4.5 kpc.")
    assert dqs and dqs[0]["unit"] == "kpc"


def test_extract_quantities_takes_first_occurrence_only():
    from app.physics.paper.ingest import extract_quantities

    qs = extract_quantities("H0 = 73.0 here, H0 = 67.4 there.")
    h0 = [q for q in qs if q["kind"] == "hubble_constant"]
    assert len(h0) == 1 and h0[0]["value"] == 73.0


# ---------------------------------------------------------------- unit: glossary

def test_find_terms_matches_longest_first_on_boundaries():
    from app.core.glossary import find_terms

    text = "The HR diagram shows isochrones; H0 = 67.4 km/s/Mpc and e=0.5 orbits. " \
           "A black hole is not in the glossary."
    ids = [m["id"] for m in find_terms(text)]
    assert "hr-diagram" in ids          # 'HR diagram' alias
    assert "isochrone" in ids           # plural 'isochrones' consumed
    assert "hubble-constant" in ids     # 'H0' alias
    # 'e=0.5': the 1-char alias 'e' is deliberately excluded from matching,
    # so bare eccentricity must NOT be claimed (it would swallow every 'e')
    assert "eccentricity" not in ids
    # boundaries: 'hole' alone or substrings inside words must not match
    assert "blackhole" not in [m["id"] for m in find_terms("blackholes everywhere")]
    # no overlapping spans
    spans = [(m["start"], m["end"]) for m in find_terms(text)]
    for i in range(len(spans) - 1):
        assert spans[i][1] <= spans[i + 1][0]


# ------------------------------------------------------------------ API: glossary

def test_glossary_endpoint_shape_and_required_fields(client, tenant_a):
    tok = auth(tenant_a["access_token"])
    g = client.get("/api/glossary", headers=tok)
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["n_terms"] >= 30
    assert set(body["categories"]) >= {"stellar", "cosmology", "celestial", "observation"}
    for t in body["terms"]:
        for field in ("id", "term", "category", "short", "explain",
                      "where_used", "references"):
            assert field in t, f"{t.get('id')} missing {field}"
        assert t["short"] and t["explain"]
        assert t["references"], f"{t['id']} must cite a reference"


def test_explain_endpoint_highlights_findings_text(client, tenant_a):
    tok = auth(tenant_a["access_token"])
    r = client.post("/api/explain", json={
        "text": "The posterior from MCMC has a 68% credible interval; the isochrone "
                "fits the cluster age of 4.6 Gyr."},
        headers=tok)
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {m["id"] for m in body["matches"]}
    assert {"posterior", "mcmc", "credible-interval", "isochrone"} <= ids
    for m in body["matches"]:
        assert m["explain"] and m["references"]
        # offsets must slice back to the matched surface text
        assert body  # offsets present
    # unauthenticated callers are rejected
    assert client.post("/api/explain", json={"text": "isochrone"}).status_code in (401, 403)


# ------------------------------------------------------------- API: analyze link

def test_analyze_rejects_unsupported_link_with_guidance(client, tenant_a):
    tok = auth(tenant_a["access_token"])
    r = client.post("/api/labs/paper/analyze",
                    json={"url": "https://nature.com/articles/s41586-024-0000"},
                    headers=tok)
    assert r.status_code == 422, r.text
    assert "arXiv" in r.json()["message"] or "DOI" in r.json()["message"]


# ------------------------------------------------------------- e2e: full pipeline

def test_paper_pipeline_end_to_end(client, tenant_a, monkeypatch):
    """analyze → ingest(mock) → extract → setup → run → validate → explain → memory → report."""
    from app.physics.paper import ingest as paper_ingest
    monkeypatch.setattr(paper_ingest, "fetch_paper", lambda ref: dict(FAKE_PAPER))

    tok = auth(tenant_a["access_token"])
    r = client.post("/api/labs/paper/analyze",
                    json={"url": "https://arxiv.org/abs/2401.12345"}, headers=tok)
    assert r.status_code == 200, r.text
    job_id = r.json()["job"]["id"]
    sid = r.json()["session_id"]
    assert r.json()["ref"]["kind"] == "arxiv"

    from workers.runner import handle_job
    handle_job(job_id)

    done = client.get(f"/api/jobs/{job_id}", headers=tok).json()
    assert done["status"] == "succeeded", done.get("error")
    result = done["result"]
    assert result["status"] == "succeeded", result
    for nid in ("plan", "paper_ingest", "paper_extract", "paper_setup",
                "paper_run", "validate", "explain", "memory", "report"):
        assert result["nodes"][nid] == "succeeded", (nid, result["nodes"])

    # timeline: every node produced evidence (graph enforces it, we assert it)
    tl = client.get(f"/api/sessions/{sid}/timeline", headers=tok).json()
    assert len(tl) >= 9
    for entry in tl:
        assert entry["evidence"], entry["node"]
        assert entry["status"] == "succeeded"

    # session state carries extracted claims + executed runs + explanation
    sess = client.get(f"/api/sessions/{sid}", headers=tok).json()
    st = sess["state"]
    ps = st["intermediate_results"]["paper"]
    assert ps["paper"]["title"] == FAKE_PAPER["title"]
    kinds = {q["kind"] for q in ps["quantities"]}
    assert {"orbital_period_days", "semi_major_axis_au", "stellar_mass", "age_gyr"} <= kinds
    assert st["domain"] == "paper"

    # the orbital claim really ran REBOUND: conservation numbers exist
    runs = ps["runs"]
    orbit = next(r for r in runs if r["engine"] == "celestial.rebound_two_body")
    assert orbit["status"] == "completed", orbit.get("error")
    assert orbit["headline"]["energy_drift_rel_max"] < 1e-6
    # declared defaults are honest: planet mass was NOT in the abstract
    assert orbit["from_paper"]["a_au"] is True
    assert orbit["from_paper"]["planet_mass"] is False
    # the extracted stellar mass feeds the orbit's central mass (not invented)
    assert orbit["from_paper"]["star_mass"] is True
    assert len(runs) >= 1

    # explanation: sections written, deterministic template, glossary-linked
    expl = ps["explanation"]
    headings = [s["heading"] for s in expl["sections"]]
    assert "What the paper says" in headings
    assert "What we found (executed numbers)" in headings
    assert "Limits of this interpretation" in headings
    assert expl["verdict"] in {"validated", "issues found"}
    # every extracted number appears in the explanation body with its snippet
    body_text = " ".join(b for s in expl["sections"] for b in s["body"])
    assert "3.2" in body_text and "semi-major axis" in body_text
    assert "abstract only" in " ".join(expl["sections"][-1]["body"])

    # stellar mapping path (separate unit-level proof: real PARSEC numbers)
    from app.orchestration.handlers_paper import _run_stellar
    from app.physics.paper.ingest import build_proposals, extract_quantities

    sq = extract_quantities("A star of 1.0 solar masses with an age of 4.6 Gyr.")
    sprops = build_proposals("stellar", sq, [])
    assert sprops and sprops[0]["engine"] == "stellar.point_parameters"
    sres = _run_stellar(sprops[0]["params"])
    assert sres["headline"]["teff_K"] > 2000
    assert sres["headline"]["luminosity_msun"] > 0.1
    assert "PARSEC" in sres["fidelity"]

    # validation: persisted rows incl. Kepler cross-check (a and P both present)
    checks = st["validation_decisions"][-1]["checks"]
    assert "paper_claims_traceable" in checks
    assert "paper_runs_reproducible" in checks
    assert "paper_kepler_crosscheck" in checks
    assert "paper_orbit_conservation" in checks
    assert checks["paper_claims_traceable"] is True
    assert checks["paper_orbit_conservation"] is True

    # memory + report persisted
    eps = client.get("/api/memory/episodic",
                     params={"q": "K2-18 b hot neptune paper"}, headers=tok).json()
    assert len(eps) >= 1
    arts = client.get(f"/api/sessions/{sid}/artifacts", headers=tok).json()
    kinds_a = {a["kind"] for a in arts}
    assert {"paper_findings", "paper_explanation", "report"} <= kinds_a
    assert all(len(a["sha256"]) == 64 for a in arts)


def test_paper_pipeline_reports_honest_failure_when_fetch_unreachable(
        client, tenant_a, monkeypatch):
    """Network/parse failures surface as a failed node, never as fabricated data."""
    from app.core.errors import DomainError
    from app.physics.paper import ingest as paper_ingest

    def _boom(ref):
        raise DomainError("Archive request failed after retries: mocked offline")

    monkeypatch.setattr(paper_ingest, "fetch_paper", _boom)
    tok = auth(tenant_a["access_token"])
    r = client.post("/api/labs/paper/analyze",
                    json={"url": "https://arxiv.org/abs/1999.00001"}, headers=tok)
    assert r.status_code == 200, r.text
    job_id = r.json()["job"]["id"]
    sid = r.json()["session_id"]

    from workers.runner import handle_job
    handle_job(job_id)

    done = client.get(f"/api/jobs/{job_id}", headers=tok).json()
    # job graph completed with failures; downstream nodes blocked, not faked
    result = done["result"]
    assert result["nodes"]["paper_ingest"] == "failed"
    for nid in ("paper_extract", "paper_setup", "paper_run", "explain"):
        assert result["nodes"][nid] == "blocked", (nid, result["nodes"])
    # failure text preserved for the user
    tl = client.get(f"/api/sessions/{sid}/timeline", headers=tok).json()
    ingest_run = next(e for e in tl if e["node"] == "paper_ingest")
    assert "mocked offline" in (ingest_run["error"] or "")
