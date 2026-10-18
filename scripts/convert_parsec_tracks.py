"""Curate PARSEC (Rosenfield EEP-matched) stellar tracks into a compact CSV.

Source: https://philrosenfield.github.io/padova_tracks/
Release: https://github.com/philrosenfield/padova_tracks/releases/tag/v2.0
(v2.0, releasev2.tar.gz -> per-metallicity tarballs -> match_*.dat files).

Input format (per the source README): six columns —
    log Age [yr], Mass [Msun], log Teff [K], Mbol [mag], log g [cgs], C/O
where Mbol and log g were derived by the source from log Teff, log L, mass:
    Mbol = 4.77 - 2.5 log L      =>  log L = (4.77 - Mbol) / 2.5
    log g = -10.616 + log M + 4 log Teff - log L
Inverting log g for radius (g = GM/R^2, solar log g = 4.438):
    R/Rsun = sqrt( (M/Msun) * 10^(4.438 - log g) )

Usage:
    python scripts/convert_parsec_tracks.py \
        --src /path/to/Z0.014Y0.273 --masses 0.1,0.5,1.0,10.0,40.0 \
        --out backend/app/physics/stellar/data/parsec_solar_tracks.csv
"""
import argparse
import csv
import datetime as dt
import json
import math
import re
from pathlib import Path

SOLAR_LOGG = 4.438  # cgs, IAU nominal solar surface gravity
MASS_RE = re.compile(r"_M([0-9]+\.[0-9]+)\.dat$")

# Curated masses: dense coverage of the low-mass regime the Stellar Lab's
# reference comparisons use, plus representatives up to the O-star range.
DEFAULT_MASSES = [
    0.10, 0.14, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90,
    1.00, 1.10, 1.25, 1.50, 2.00, 2.40, 3.00, 4.00, 6.00, 8.00,
    10.00, 12.00, 16.00, 20.00, 24.00, 30.00, 40.00, 60.00, 100.00,
]
MAX_POINTS_PER_TRACK = 150


def find_track(src: Path, mass: float) -> Path | None:
    want = f"M{mass:07.3f}.dat"
    for p in sorted(src.glob("*.dat")):
        if p.name.startswith("._"):  # macOS AppleDouble resource forks
            continue
        if p.name.endswith(want) and "HB" not in p.name:
            return p
    return None


def convert_track(path: Path, initial_mass: float) -> list[dict]:
    rows = []
    bad = 0
    with open(path, encoding="latin-1") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) < 5:
                bad += 1
                continue
            try:
                log_age, mass, log_te, mbol, logg = (float(x) for x in parts[:5])
            except ValueError:
                bad += 1  # stray binary/metadata bytes seen in a few files
                continue
            log_lum = (4.77 - mbol) / 2.5
            radius = math.sqrt(mass * 10 ** (SOLAR_LOGG - logg))
            rows.append({
                "initial_mass_msun": initial_mass,
                "mass_msun": round(mass, 4),
                "log_age_yr": round(log_age, 5),
                "log_teff": round(log_te, 5),
                "log_lum": round(log_lum, 5),
                "log_g": round(logg, 4),
                "radius_rsun": round(radius, 5),
            })
    if not rows or bad > len(rows):
        raise RuntimeError(f"{path.name}: unusable ({len(rows)} good, {bad} bad lines)")
    # Monotonic-age dedup then uniform downsample
    rows = [r for i, r in enumerate(rows)
            if i == 0 or r["log_age_yr"] > rows[i - 1]["log_age_yr"]]
    if len(rows) > MAX_POINTS_PER_TRACK:
        step = math.ceil(len(rows) / MAX_POINTS_PER_TRACK)
        rows = rows[::step] + [rows[-1]]
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="directory of match_*.dat files")
    ap.add_argument("--out", required=True, help="output CSV path")
    ap.add_argument("--masses", default=",".join(str(m) for m in DEFAULT_MASSES))
    ap.add_argument("--z", type=float, default=0.014)
    ap.add_argument("--y", type=float, default=0.273)
    ap.add_argument("--prov", default=None,
                    help="provenance JSON path (default: <out stem>_provenance.json)")
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    masses = [float(m) for m in args.masses.split(",")]

    fieldnames = ["initial_mass_msun", "mass_msun", "log_age_yr", "log_teff",
                  "log_lum", "log_g", "radius_rsun", "metallicity_z", "helium_y"]
    used, skipped = [], []
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for m in masses:
            track = find_track(src, m)
            if track is None:
                skipped.append(m)
                continue
            for row in convert_track(track, initial_mass=m):
                row["metallicity_z"] = args.z
                row["helium_y"] = args.y
                w.writerow(row)
            used.append(m)

    prov = {
        "dataset": "PARSEC v1.2S stellar evolution tracks (EEP-matched v2.0)",
        "source_page": "https://philrosenfield.github.io/padova_tracks/",
        "source_release": "https://github.com/philrosenfield/padova_tracks/releases/tag/v2.0",
        "downloaded_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metallicity_z": args.z,
        "helium_y": args.y,
        "masses_msun": used,
        "masses_skipped": skipped,
        "n_rows": sum(1 for _ in open(out)) - 1,
        "max_points_per_track": MAX_POINTS_PER_TRACK,
        "derived_columns": {
            "log_lum": "log L = (4.77 - Mbol) / 2.5  [inverted from source Mbol]",
            "radius_rsun": "R/Rsun = sqrt((M/Msun) * 10^(4.438 - log g))  [inverted from source log g]",
        },
        "citations": [
            "Bressan et al. 2012, MNRAS, 427, 127 (PARSEC v1.2S)",
            "Chen et al. 2014, MNRAS, 444, 2525 (low-mass updates)",
            "Tang et al. 2014, MNRAS, 445, 4287 (high-mass updates)",
            "Rosenfield et al. 2016, ApJ, 822, 73 (TP-AGB)",
            "Dotter 2016, ApJS, 222, 8 (EEP definitions)",
        ],
        "license_note": ("No explicit data license found on the source pages; "
                         "tracks are published for scientific use with the "
                         "citations above. Redistribution here is a curated "
                         "scientific dataset with full provenance."),
    }
    prov_path = Path(args.prov) if args.prov else out.with_name(out.stem + "_provenance.json")
    prov_path.write_text(json.dumps(prov, indent=2))
    print(f"wrote {out} ({prov['n_rows']} rows, {len(used)} tracks, skipped={skipped})")
    print(f"wrote {prov_path}")


if __name__ == "__main__":
    main()