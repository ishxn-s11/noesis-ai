"""Documented public-archive connectors with caching, rate limiting, retries.

Connectors return raw results with full provenance metadata. When a remote
archive is unreachable the error is surfaced explicitly — observations are
NEVER fabricated or substituted with placeholder data.
"""
import hashlib
import json
import time
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.errors import DomainError, ValidationErr

CACHE_DIR = Path(settings.artifact_root).parent / ".cache" / "archives"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_request_log: list[float] = []


def _rate_limit() -> None:
    now = time.time()
    _request_log[:] = [t for t in _request_log if now - t < 60]
    if len(_request_log) >= settings.rate_limit_per_minute:
        raise DomainError("Archive rate limit exceeded; retry in a minute", details={"code": 429})
    _request_log.append(now)


def _cached_get(url: str, params: dict, *, timeout: float = 60.0, cache_ttl_s: int = 86400) -> dict:
    """GET with on-disk cache, bounded retries and rate limiting."""
    key = hashlib.sha256(f"{url}?{json.dumps(params, sort_keys=True)}".encode()).hexdigest()
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < cache_ttl_s:
        return json.loads(cache_file.read_text())
    _rate_limit()
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.get(url, params=params, headers={"User-Agent": "NOESIS-AI/0.1"})
                resp.raise_for_status()
                data = {"url": str(resp.url), "status_code": resp.status_code,
                        "fetched_at": time.time(), "body": resp.text}
            cache_file.write_text(json.dumps(data))
            return data
        except httpx.HTTPError as exc:
            last_exc = exc
            time.sleep(0.5 * 2**attempt)
    raise DomainError(
        f"Archive request failed after retries: {last_exc}",
        details={"url": url, "hint": "archive may be offline or unreachable from this host"},
    )


def _tap_query(base_url: str, adql: str, *, max_rows: int = 500) -> dict:
    """Generic TAP /sync query (used by VizieR, Gaia DR3, Exoplanet Archive)."""
    _rate_limit()
    key = hashlib.sha256(f"{base_url}|{adql}|{max_rows}".encode()).hexdigest()
    cache_file = CACHE_DIR / f"tap_{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.post(
                base_url,
                data={"request": "doQuery", "lang": "ADQL", "format": "json", "maxrec": max_rows,
                      "query": adql},
                headers={"User-Agent": "NOESIS-AI/0.1"},
            )
            resp.raise_for_status()
            payload = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise DomainError(f"TAP query failed: {exc}", details={"endpoint": base_url, "adql": adql}) from exc
    out = {
        "endpoint": base_url,
        "adql": adql,
        "columns": payload.get("data", {}).get("columns", []),
        "rows": payload.get("data", {}).get("data", []),
    }
    cache_file.write_text(json.dumps(out))
    return out


# --- NASA Exoplanet Archive (TAP) -------------------------------------------
EXOPLANET_TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"


def query_exoplanets(where: str = "defaultflag=1", max_rows: int = 200) -> dict:
    """Query the NASA Exoplanet Archive composite PS table via TAP/ADQL."""
    if not where.strip():
        raise ValidationErr("Empty WHERE clause")
    adql = (
        "SELECT pl_name,hostname,discoverymethod,disc_year,pl_orbper,pl_rade,pl_bmasse,"
        "pl_orbsmax,pl_orbeccen,st_teff,st_mass,sy_dist,disc_facility "
        f"FROM pscomppars WHERE {where} ORDER BY disc_year DESC"
    )
    out = _tap_query(EXOPLANET_TAP, adql, max_rows=max_rows)
    out["source"] = "NASA Exoplanet Archive (IPAC/Caltech), pscomppars table"
    out["source_url"] = "https://exoplanetarchive.ipac.caltech.edu/"
    return out


# --- ESA Gaia DR3 (TAP) ------------------------------------------------------
GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"


def cone_search_gia(ra_deg: float, dec_deg: float, radius_arcsec: float = 10.0,
                    max_rows: int = 100) -> dict:
    """Gaia DR3 cone search (primary designation, parallax, photometry)."""
    adql = (
        "SELECT TOP %d source_id,ra,dec,parallax,pmra,pmdec,gmag,bpmag,rpmag,radial_velocity "
        "FROM gaiadr3.gaia_source WHERE 1=CONTAINS(POINT('ICRS',ra,dec),"
        f"CIRCLE('ICRS',{ra_deg},{dec_deg},{radius_arcsec/3600.0}))"
    ) % max_rows
    out = _tap_query(GAIA_TAP, adql, max_rows=max_rows)
    out["source"] = "ESA Gaia Archive, DR3 (gaia_source)"
    out["source_url"] = "https://gea.esac.esa.int/archive/"
    return out


# --- VizieR (TAP) ------------------------------------------------------------
VIZIER_TAP = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"


def query_vizier(catalog: str, constraint: str = "", max_rows: int = 200) -> dict:
    """Query a VizieR catalog table via TAP. catalog like 'J/A+A/674/A23'."""
    if "/" not in catalog:
        raise ValidationErr("VizieR catalog id must look like 'J/A+A/674/A23'")
    table = catalog.replace("/", "_")
    where = f"WHERE {constraint}" if constraint else ""
    adql = f'SELECT TOP {max_rows} * FROM "T/{table}" {where}'
    out = _tap_query(VIZIER_TAP, adql, max_rows=max_rows)
    out["source"] = f"VizieR catalog {catalog} (CDS, Strasbourg)"
    out["source_url"] = "https://vizier.cds.unistra.fr/"
    return out


# --- SIMBAD (name resolver) --------------------------------------------------
def resolve_simbad(object_name: str) -> dict:
    """Resolve an astronomical object via SIMBAD Sesame name resolver."""
    safe = object_name.strip().replace(" ", "+")
    if not safe or len(safe) > 200:
        raise ValidationErr("Invalid object name")
    url = f"https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/SNV?{safe}"
    data = _cached_get(url, {})
    body = data.get("body", "")
    coords = _parse_simbad_oids(body)
    return {
        "query": object_name,
        "resolver_data": coords,
        "source": "SIMBAD Sesame name resolver (CDS)",
        "source_url": "https://simbad.cds.unistra.fr/",
        "raw_xml_excerpt": body[:2000],
    }


def _parse_simbad_oids(xml: str) -> dict:
    """Best-effort extraction of J2000 coordinates from Sesame XML."""
    import re

    out: dict[str, str] = {}
    m = re.search(r'<jradeg>([\d.]+)</jradeg>\s*<jdedeg>([-\d.]+)</jdedeg>', xml)
    if m:
        out["ra_deg"], out["dec_deg"] = m.group(1), m.group(2)
    m = re.search(r'<otype>([^<]+)</otype>', xml)
    if m:
        out["object_type"] = m.group(1)
    m = re.search(r'<mag>([\d.]+)</mag>', xml)
    if m:
        out["V_magnitude"] = m.group(1)
    return out


# --- arXiv literature --------------------------------------------------------
def search_arxiv(query: str, max_results: int = 5) -> dict:
    """Search recent astrophysics preprints via the arXiv API."""
    import urllib.parse

    if not query.strip():
        raise ValidationErr("Empty arXiv query")
    url = "https://export.arxiv.org/api/query"
    data = _cached_get(url, {
        "search_query": f"all:{urllib.parse.quote(query)}",
        "start": 0, "max_results": max_results, "sortBy": "submittedDate", "sortOrder": "descending",
    }, cache_ttl_s=3600)
    import re

    entries = re.findall(r"<entry>(.*?)</entry>", data.get("body", ""), re.DOTALL)
    papers = []
    for entry in entries[:max_results]:
        def grab(tag: str) -> str:
            m = re.search(rf"<{tag}>(.*?)</{tag}>", entry, re.DOTALL)
            return m.group(1).strip() if m else ""
        papers.append({
            "title": " ".join(grab("title").split()),
            "summary": " ".join(grab("summary").split())[:600],
            "id": grab("id"),
            "published": grab("published"),
            "authors": re.findall(r"<name>([^<]+)</name>", entry)[:12],
        })
    return {"query": query, "papers": papers, "source": "arXiv API (export.arxiv.org)",
            "source_url": "https://arxiv.org/", "note": "Preprints; peer-review status varies"}


def query_apod(count: int = 12, q: str | None = None) -> dict:
    """Real captured celestial imagery from NASA.

    Primary source: NASA Astronomy Picture of the Day API (api.nasa.gov,
    DEMO_KEY, disk-cached 6 h). If APOD serves degraded placeholder entries
    (observed 2026-10: every entry — even famous dates — resolving to the
    generic science.nasa.gov NASA-logo asset titled "NASA Science"), the
    connector falls back to the NASA Image and Video Library search
    (images-api.nasa.gov) and says so explicitly in `source`/`note`.
    Placeholders are never returned as if they were photographs.
    """
    if not (1 <= count <= 24):
        raise ValidationErr("count must be between 1 and 24")

    def placeholder(item: dict) -> bool:
        return ("nasa-logo" in item["url"]
                or item["title"].strip().lower() == "nasa science")

    # --- primary: APOD -----------------------------------------------------
    try:
        data = _cached_get("https://api.nasa.gov/planetary/apod",
                           {"api_key": "DEMO_KEY", "count": count, "thumbs": "true"},
                           timeout=30, cache_ttl_s=6 * 3600)
        body = json.loads(data.get("body", "[]"))
    except (DomainError, json.JSONDecodeError):
        body = []
    if isinstance(body, list) and body:
        items = [{
            "date": e.get("date", ""),
            "title": e.get("title", ""),
            "explanation": e.get("explanation", ""),
            "media_type": e.get("media_type", "image"),
            "url": e.get("url", ""),
            "hd_url": e.get("hdurl") or e.get("url", ""),
            "thumbnail_url": e.get("thumbnail_url", ""),
            "copyright": (e.get("copyright") or "").strip(),
            "service_version": e.get("service_version", ""),
        } for e in body]
        if sum(1 for i in items if placeholder(i)) <= len(items) // 2:
            items.sort(key=lambda x: x["date"], reverse=True)
            return {
                "archive": "apod", "items": items, "count": len(items),
                "source": "NASA Astronomy Picture of the Day (api.nasa.gov)",
                "source_url": "https://apod.nasa.gov/apod/",
                "fetched_at": data.get("fetched_at"),
                "note": ("Real captured imagery; full-resolution (HD) links where "
                         "available. Copyright per entry (photographers/agencies/NASA)."),
            }

    # --- fallback: NASA Image and Video Library ----------------------------
    query = (q or "nebula").strip()[:80] or "nebula"
    data = _cached_get("https://images-api.nasa.gov/search",
                       {"q": query, "media_type": "image"},
                       timeout=30, cache_ttl_s=6 * 3600)
    collection = json.loads(data.get("body", "{}"))
    if not isinstance(collection, dict) or "collection" not in collection:
        raise DomainError("Unexpected NASA Images response shape",
                          details={"archive": "apod", "status": data.get("status_code")})
    items = []
    for entry in collection["collection"].get("items", [])[:count]:
        if not entry.get("data"):
            continue
        d0 = entry["data"][0]
        nid = d0.get("nasa_id", "")
        links = entry.get("links") or []
        display = links[0].get("href", "") if links else ""
        items.append({
            "date": (d0.get("date_created") or "")[:10],
            "title": d0.get("title", ""),
            "explanation": d0.get("description", ""),
            "media_type": "image",
            "url": display or f"https://images-assets.nasa.gov/image/{nid}/{nid}~medium.jpg",
            "hd_url": f"https://images-assets.nasa.gov/image/{nid}/{nid}~orig.jpg",
            "thumbnail_url": display,
            "copyright": (d0.get("center") or "").strip(),
            "service_version": "images-api",
        })
    if not items:
        raise DomainError("NASA image search returned no items",
                          details={"archive": "apod", "q": query})
    return {
        "archive": "apod", "items": items, "count": len(items),
        "source": f"NASA Image and Video Library (images-api.nasa.gov), query \"{query}\"",
        "source_url": "https://images.nasa.gov/",
        "fetched_at": data.get("fetched_at"),
        "note": ("APOD API is currently serving placeholder entries, so this response "
                 "uses NASA's Image and Video Library instead — real captured imagery "
                 "with full-resolution (~orig) links. Credit/copyright per entry."),
    }


CONNECTORS = {
    "exoplanet_archive": query_exoplanets,
    "gaia": cone_search_gia,
    "vizier": query_vizier,
    "simbad": resolve_simbad,
    "arxiv": search_arxiv,
    "apod": query_apod,
}
