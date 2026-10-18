"""Research-paper ingestion: URL → metadata + extracted quantities + engine proposals.

Supports arXiv links (abs/pdf, all id styles) and DOI links (via Crossref).
Fetching reuses the platform's cached, rate-limited, retrying connector
(`connectors._cached_get`); when a remote source is unreachable the error is
surfaced explicitly — paper data is NEVER fabricated.

Extraction is deterministic regex parsing of the ABSTRACT ONLY (full PDF text
is not parsed — stated honestly in every response). Each extracted quantity
carries the literal text snippet it was matched from, so the platform can show
exactly which words in the paper support each number it later uses.
"""
import re
import xml.etree.ElementTree as ET

from app.core.errors import ValidationErr
from app.physics.observations.connectors import _cached_get

ARXIV_API = "https://export.arxiv.org/api/query"
CROSSREF_API = "https://api.crossref.org/works"

# arXiv ids: 2401.12345 [vN]  |  old-style archive/YYMMNNN [vN]
_ARXIV_NEW = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
_ARXIV_OLD = re.compile(r"([a-z-]+(\.[A-Z]{2})?/\d{7})(v\d+)?")

DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)")


def parse_paper_ref(url: str) -> dict:
    """Classify a paper reference. Returns {kind: arxiv|doi, id, url}.
    Raises ValidationErr for anything unsupported — never guesses."""
    raw = (url or "").strip()
    if not raw:
        raise ValidationErr("Empty paper link")
    low = raw.lower()

    if "arxiv.org" in low or low.startswith("arxiv:") or \
            re.fullmatch(r"(\d{4}\.\d{4,5}|[a-z-]+/\d{7})(v\d+)?", raw):
        m = _ARXIV_NEW.search(raw) or _ARXIV_OLD.search(raw)
        if not m:
            raise ValidationErr(
                "Could not find an arXiv id in the link — expected e.g. "
                "https://arxiv.org/abs/2401.12345")
        return {"kind": "arxiv", "id": m.group(1), "url": raw}

    m = DOI_RE.search(raw)
    if m:
        return {"kind": "doi", "id": m.group(1).rstrip("."), "url": raw}

    raise ValidationErr(
        "Unsupported paper link. Paste an arXiv link (abs or pdf) or a DOI "
        "link (https://doi.org/10.xxxx/xxxxx); other publishers require "
        "paywall access this platform does not have.")


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def fetch_paper(ref: dict) -> dict:
    """Fetch real metadata for a parsed paper reference (cached, retried)."""
    if ref["kind"] == "arxiv":
        data = _cached_get(ARXIV_API, {"id_list": ref["id"]},
                           timeout=30, cache_ttl_s=7 * 86400)
        return _parse_arxiv_atom(data.get("body", ""), ref)
    data = _cached_get(f"{CROSSREF_API}/{ref['id']}", {},
                       timeout=30, cache_ttl_s=7 * 86400)
    return _parse_crossref(data.get("body", ""), ref)


def _parse_arxiv_atom(xml_text: str, ref: dict) -> dict:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValidationErr(f"arXiv returned unparseable XML: {exc}") from exc
    entry = next((e for e in root.iter() if _strip_ns(e.tag) == "entry"), None)
    if entry is None:
        raise ValidationErr(f"arXiv id {ref['id']} not found (no <entry>)")

    def text(tag: str) -> str:
        el = next((c for c in entry if _strip_ns(c.tag) == tag), None)
        return " ".join((el.text or "").split()) if el is not None else ""

    authors = [" ".join((next(
        (c.text for c in a if _strip_ns(c.tag) == "name"), "") or "").split())
        for a in entry if _strip_ns(a.tag) == "author"]
    doi = ""
    for c in entry:
        if _strip_ns(c.tag) == "doi":
            doi = (c.text or "").strip()
    return {
        "kind": "arxiv", "id": ref["id"],
        "url": f"https://arxiv.org/abs/{ref['id']}",
        "title": text("title"),
        "authors": authors[:50],
        "abstract": text("summary"),
        "published": text("published")[:10],
        "doi": doi,
        "source": "arXiv API (export.arxiv.org)",
    }


def _parse_crossref(json_text: str, ref: dict) -> dict:
    import json

    try:
        msg = json.loads(json_text).get("message", {})
    except json.JSONDecodeError as exc:
        raise ValidationErr(f"Crossref returned unparseable JSON: {exc}") from exc
    title = (msg.get("title") or [""])[0]
    if not title:
        raise ValidationErr(f"DOI {ref['id']} not found in Crossref")
    authors = [" ".join(filter(None, [a.get("given", ""), a.get("family", "")]))
               for a in msg.get("author", [])[:50]]
    abstract = re.sub(r"<[^>]+>", " ", msg.get("abstract", "") or "")
    return {
        "kind": "doi", "id": ref["id"],
        "url": msg.get("URL", f"https://doi.org/{ref['id']}"),
        "title": " ".join(title.split()),
        "authors": authors,
        "abstract": " ".join(abstract.split()),
        "published": str((msg.get("published", {}).get("date-parts")
                          or [[""]])[0][0] or ""),
        "doi": ref["id"],
        "source": "Crossref REST API",
    }


# ------------------------------------------------------------------ extraction

# Each pattern: (kind, regex, unit, note). Values are matched from the abstract
# with surrounding context preserved — no interpretation beyond the literal text.
_QUANTITY_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("hubble_constant",
     re.compile(r"H[_\s]?[0O₀]\s*(?:=|of|is|=)\s*([0-9]{2}(?:\.[0-9]+)?)"
                r"|(?:Hubble constant[^.]{0,40}?)([0-9]{2}(?:\.[0-9]+)?)"
                r"|([0-9]{2}(?:\.[0-9]+)?)\s*(?:±\s*[0-9.]+\s*)?km\s*s?[⁻\-\s]*1?\s*Mpc"),
     "km/s/Mpc"),
    ("omega_m",
     re.compile(r"Ω[_\s]?[mM]\s*(?:=|of|is)\s*(0?\.[0-9]{2,3})"
                r"|\bOmega[_\s]?m[^0-9]{0,8}(0?\.[0-9]{2,3})"),
     "dimensionless"),
    ("redshift",
     re.compile(r"\bz\s*(?:=|of)\s*([0-9]+(?:\.[0-9]+)?)"),
     "dimensionless"),
    ("stellar_mass",
     re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(?:M[_\s]?[{]?(?:⊙|sun|sun)[}]?|M_⊙|solar masses?|M_\{⊙\}|M☉)",
                re.IGNORECASE),
     "M☉"),
    ("planet_mass_jup",
     re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(?:M[_\s]?[jJ]|jupiter masses?|Jupiter masses?)"),
     "M_J"),
    ("planet_mass_earth",
     re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(?:M[_\s]?[eE]|earth masses?|Earth masses?|M⊕)"),
     "M_E"),
    ("orbital_period_days",
     re.compile(r"(?:period[^.]{0,30}?)([0-9]+(?:\.[0-9]+)?)\s*(?:days?|d)\b"
                r"|\b([0-9]+(?:\.[0-9]+)?)\s*(?:days?)\s*(?:period|orbit)",),
     "days"),
    ("semi_major_axis_au",
     re.compile(r"(?:semi-?major axis[^.]{0,20}?)([0-9]+(?:\.[0-9]+)?)\s*(?:AU|au)"
                r"|\ba\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*AU"),
     "AU"),
    ("teff",
     re.compile(r"([0-9]{3,5})\s*K\b(?=[^.]{0,40}(?:T|t)eff|temperature)"),
     "K"),
    ("age_gyr",
     re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*Gyr"),
     "Gyr"),
    ("distance_pc",
     re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(kpc|Mpc|pc)\b"),
     "pc"),
]

_OBJECT_NAME_RE = re.compile(
    r"\b(HD\s?\d{3,8}|HIP\s?\d{3,8}|TRAPPIST-1|Kepler-\d+|TOI-\d+|"
    r"Proxima Centauri|Sirius|Vega|Betelgeuse|Ross\s?128|GJ\s?\d{3,4}|"
    r"NGC\s?\d{2,4}|Messier\s?M?\d{1,3})\b", re.IGNORECASE)

_SUBDOMAIN_KEYWORDS = {
    "cosmology": ["hubble", "redshift", "dark energy", "lambda", "Ω", "cosmolog",
                  "expansion", "cmb", "supernovae type ia", "comoving"],
    "stellar": ["stellar", "star ", "main sequence", "teff", "photosphere",
                "spectral", "luminosity of", "parsec tracks", "metallicity"],
    "celestial": ["orbit", "orbital", "exoplanet", "planet ", "binary",
                  "period of", "semi-major", "kepler", "n-body", "stability"],
}


def extract_quantities(text: str) -> list[dict]:
    """Deterministic regex extraction of quantities from abstract text.

    Each hit records the literal snippet it came from — the caller can always
    show which words in the paper support the number.
    """
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for kind, pat, unit in _QUANTITY_PATTERNS:
        for m in pat.finditer(text):
            groups = [g for g in m.groups() if g]
            if not groups:
                continue
            value, *rest = groups
            try:
                num = float(value)
            except ValueError:
                continue
            # a non-numeric trailing group is the literal unit (e.g. 'kpc' vs 'pc')
            unit_use = unit
            for r in rest:
                try:
                    float(r)
                except ValueError:
                    unit_use = r
                    break
            start = max(0, m.start() - 60)
            snippet = text[start:m.end() + 40].strip()
            key = (kind, f"{num:.6g}")
            if key in seen:
                continue
            seen.add(key)
            found.append({"kind": kind, "value": num, "unit": unit_use,
                          "snippet": snippet})
            break  # first occurrence per kind: abstracts state headline numbers once
    return found


def detect_subdomain(title: str, abstract: str) -> tuple[str, dict]:
    """Keyword-score the paper into cosmology|stellar|celestial|observation."""
    blob = f"{title} {abstract}".lower()
    scores = {d: sum(1 for kw in kws if kw in blob)
              for d, kws in _SUBDOMAIN_KEYWORDS.items()}
    best = max(scores, key=lambda d: scores[d])
    if scores[best] == 0:
        return "celestial", scores  # engine-rich default; labeled as such
    return best, scores


def find_object_names(text: str) -> list[str]:
    seen: list[str] = []
    for m in _OBJECT_NAME_RE.finditer(text):
        name = " ".join(m.group(0).split())
        if name.lower() not in {s.lower() for s in seen}:
            seen.append(name)
    return seen[:10]


# ------------------------------------------------------------------- proposals

def build_proposals(subdomain: str, quantities: list[dict],
                    object_names: list[dict] | list[str]) -> list[dict]:
    """Map extracted quantities onto concrete engine runs.

    Every proposal declares which parameters came from the paper's abstract
    and which are platform defaults — nothing is silently invented.
    """
    by_kind = {q["kind"]: q for q in quantities}
    proposals: list[dict] = []

    if subdomain == "cosmology":
        h0q = by_kind.get("hubble_constant")
        omq = by_kind.get("omega_m")
        zq = by_kind.get("redshift")
        proposals.append({
            "id": "cosmo_distance_ladder",
            "engine": "cosmology.distance_ladder",
            "label": "Flat-ΛCDM distance ladder at the paper's cosmology",
            "params": {
                "H0": h0q["value"] if h0q else 67.4,
                "Om0": omq["value"] if omq else 0.315,
                "z_max": min(max(zq["value"], 2.0), 10.0) if zq else 2.0,
            },
            "from_paper": {k: bool(q) for k, q in
                           (("H0", h0q), ("Om0", omq), ("z", zq))},
            "justification": (
                "Distance ladder, expansion history and cosmic age computed at the "
                "paper's stated parameters"
                + (f" (H0={h0q['value']} km/s/Mpc from abstract)" if h0q
                   else " (H0 not stated in abstract — Planck18 default 67.4 used)")
            ),
        })

    if subdomain == "stellar":
        mq = by_kind.get("stellar_mass")
        ageq = by_kind.get("age_gyr")
        proposals.append({
            "id": "stellar_point_params",
            "engine": "stellar.point_parameters",
            "label": "Published PARSEC track parameters for the paper's star",
            "params": {
                "mass_msun": mq["value"] if mq else 1.0,
                "age_yr": ageq["value"] * 1e9 if ageq else None,
            },
            "from_paper": {"mass": bool(mq), "age": bool(ageq)},
            "justification": (
                "PARSEC v1.2S track interpolation at the mass stated in the abstract"
                + (f" ({mq['value']} M☉)" if mq
                   else " (no mass in abstract — solar mass used as reference)")
            ),
        })

    if subdomain == "celestial":
        aq = by_kind.get("semi_major_axis_au")
        pq = by_kind.get("orbital_period_days")
        mj = by_kind.get("planet_mass_jup")
        me = by_kind.get("planet_mass_earth")
        m_planet_msun = None
        m_src = ""
        if mj:
            m_planet_msun = mj["value"] * 0.0009543  # M_J -> M_sun
            m_src = f"{mj['value']} M_J (Jupiter masses) from abstract"
        elif me:
            m_planet_msun = me["value"] * 3.003e-6   # M_E -> M_sun
            m_src = f"{me['value']} M_E (Earth masses) from abstract"
        if aq or pq:
            sq = by_kind.get("stellar_mass")
            proposals.append({
                "id": "rebound_two_body",
                "engine": "celestial.rebound_two_body",
                "label": "REBOUND integration of the paper's orbit",
                "params": {
                    "a_au": aq["value"] if aq else None,
                    "period_days": pq["value"] if pq else None,
                    "m_planet_msun": m_planet_msun or 1e-3,
                    "m_star_msun": sq["value"] if sq else 1.0,
                },
                "from_paper": {"a_au": bool(aq), "period_days": bool(pq),
                               "planet_mass": bool(mj or me),
                               "star_mass": bool(sq)},
                "justification": (
                    "Two-body REBOUND integration"
                    + (f" with a={aq['value']} AU from abstract" if aq else "")
                    + (f", P={pq['value']} days from abstract" if pq else "")
                    + (f", planet mass {m_src}" if m_src else
                       ", planet mass defaulted to 1 M_J (not in abstract)")
                ),
            })

    if subdomain == "observation" and object_names:
        proposals.append({
            "id": "simbad_resolve",
            "engine": "observation.simbad_resolve",
            "label": f"Resolve '{object_names[0]}' via SIMBAD",
            "params": {"object_name": object_names[0]},
            "from_paper": {"object_name": True},
            "justification": (f"Named source '{object_names[0]}' found in the "
                              "abstract; resolved via SIMBAD name service"),
        })

    return proposals
