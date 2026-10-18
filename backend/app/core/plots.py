"""Scientific plot generation (matplotlib Agg) -> PNG bytes.

Plots are pure functions of stored numerical results: no LLM involvement.
"""
import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

PALETTE = ["#4fc3f7", "#ff8a65", "#aed581", "#ba68c8", "#f06292", "#ffd54f"]


def _fig_to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def plot_trajectories_2d(sim_result: dict) -> bytes:
    bodies = sim_result["snapshots"]["bodies"]
    fig, ax = plt.subplots(figsize=(7, 7))
    for i, (name, data) in enumerate(bodies.items()):
        ax.plot(data["x"], data["y"], color=PALETTE[i % len(PALETTE)], lw=1.1, label=name)
    ax.set_aspect("equal")
    ax.set_xlabel("x [AU]")
    ax.set_ylabel("y [AU]")
    ax.legend(loc="best", fontsize=8)
    ax.set_title(f"Orbital trajectories ({sim_result['meta']['integrator']})")
    ax.grid(alpha=0.3)
    return _fig_to_png(fig)


def plot_trajectories_3d(sim_result: dict) -> bytes:
    bodies = sim_result["snapshots"]["bodies"]
    fig = plt.figure(figsize=(7, 6))
    ax = fig.add_subplot(111, projection="3d")
    for i, (name, data) in enumerate(bodies.items()):
        ax.plot(data["x"], data["y"], data["z"], color=PALETTE[i % len(PALETTE)], lw=1.0, label=name)
    ax.set_xlabel("x [AU]")
    ax.set_ylabel("y [AU]")
    ax.set_zlabel("z [AU]")
    ax.legend(loc="best", fontsize=8)
    ax.set_title("3D trajectories")
    return _fig_to_png(fig)


def plot_conservation(sim_result: dict) -> bytes:
    diag = sim_result["diagnostics"]
    t = np.asarray(sim_result["snapshots"]["time_yr"], dtype=float)
    fig, axes = plt.subplots(2, 1, figsize=(7.5, 6), sharex=True)
    axes[0].plot(t, np.asarray(diag["energy_rel_series"]), color="#4fc3f7", lw=1.2)
    axes[0].set_ylabel("ΔE/E₀")
    axes[0].set_yscale("symlog", linthresh=1e-14)
    axes[0].grid(alpha=0.3)
    axes[0].set_title("Conservation diagnostics")
    axes[1].plot(t, np.asarray(diag["angmom_rel_series"]), color="#ff8a65", lw=1.2)
    axes[1].set_ylabel("Δ|L|/L₀")
    axes[1].set_xlabel("time [yr]")
    axes[1].set_yscale("symlog", linthresh=1e-14)
    axes[1].grid(alpha=0.3)
    return _fig_to_png(fig)


def plot_energy_drift_comparison(results: list[dict]) -> bytes:
    """Bar chart comparing max |dE/E0| across sweep runs."""
    labels = [r.get("label", f"run{i}") for i, r in enumerate(results)]
    drifts = [max(r.get("diagnostics", {}).get("energy_drift_rel_max", 0.0), 1e-18) for r in results]
    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 0.8), 4.5))
    ax.bar(range(len(labels)), drifts, color="#4fc3f7")
    ax.set_yscale("log")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("max |ΔE/E₀| (log)")
    ax.set_title("Energy drift across parameter sweep")
    ax.grid(alpha=0.3, axis="y")
    return _fig_to_png(fig)


def plot_hr_diagram(points: list[dict], references: list[dict] | None = None,
                    tracks: list[dict] | None = None,
                    title: str = "Hertzsprung–Russell diagram (simplified analytic models)") -> bytes:
    """HR diagram: Teff (reversed x) vs L; optional published track curves."""
    fig, ax = plt.subplots(figsize=(7.5, 6))
    for tr in tracks or []:
        ax.plot([10 ** lt for lt in tr["log_teff"]], [10 ** ll for ll in tr["log_lum"]],
                lw=1.2, alpha=0.85, label=tr.get("label", "track"))
    if points:
        teff = [p["teff_K"] for p in points]
        lum = [p.get("luminosity_msun", p.get("lum_msun", 1.0)) for p in points]
        ax.scatter(teff, lum, s=30, c="#4fc3f7", label="model stars", zorder=3)
    if references:
        rt = [r["teff_K"] for r in references]
        rl = [r["lum_msun"] for r in references]
        ax.scatter(rt, rl, s=55, marker="*", c="#ffd54f", edgecolors="k",
                   linewidths=0.5, label="literature references", zorder=4)
        for r in references:
            ax.annotate(r["name"], (r["teff_K"], r["lum_msun"]), fontsize=7,
                        xytext=(4, 4), textcoords="offset points")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.invert_xaxis()
    ax.set_xlabel("T$_{eff}$ [K]")
    ax.set_ylabel("L [L$_{\\odot}$]")
    ax.set_title(title)
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8)
    return _fig_to_png(fig)


def plot_track_grid(tracks: list[dict], references: list[dict] | None = None,
                    metallicity_z: float = 0.014) -> bytes:
    """Full-grid HR diagram for the track browser (mass-colored, with colorbar).

    `tracks` are hr_track() payloads: log_teff/log_lum curves plus ms_end
    markers, colored by initial mass on a log scale (cyan -> orange, matching
    the web view).
    """
    from matplotlib import cm
    from matplotlib import colors as mcolors

    norm = mcolors.LogNorm(vmin=min(t["grid_mass_msun"] for t in tracks),
                           vmax=max(t["grid_mass_msun"] for t in tracks))
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "mass", ["#4fc3f7", "#ffd54f", "#ff8a65"])
    annotated = {0.1, 1.0, 10.0, 100.0}

    fig, ax = plt.subplots(figsize=(8.6, 6.6))
    for tr in tracks:
        teff = 10 ** np.asarray(tr["log_teff"])
        lum = 10 ** np.asarray(tr["log_lum"])
        c = cmap(norm(tr["grid_mass_msun"]))
        label = (f"{tr['grid_mass_msun']:g} M☉"
                 if tr["grid_mass_msun"] in annotated else None)
        ax.plot(teff, lum, lw=1.1, color=c, alpha=0.9, label=label)
        if tr.get("ms_end"):
            ax.plot([10 ** tr["ms_end"]["log_teff"]], [10 ** tr["ms_end"]["log_lum"]],
                    linestyle="none", marker="x", ms=4, color=c, alpha=0.85)
    if references:
        rt = [r["teff_K"] for r in references]
        rl = [r["lum_msun"] for r in references]
        ax.scatter(rt, rl, s=55, marker="*", c="#ffd54f", edgecolors="k",
                   linewidths=0.5, label="literature references", zorder=4)
        for r in references:
            ax.annotate(r["name"], (r["teff_K"], r["lum_msun"]), fontsize=7,
                        xytext=(4, 4), textcoords="offset points")
    sm = cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label="initial mass [M☉]")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.invert_xaxis()
    ax.set_xlabel("T$_{eff}$ [K]")
    ax.set_ylabel("L [L$_{\\odot}$]")
    ax.set_title(f"PARSEC v1.2S evolutionary tracks — Z={metallicity_z:g} "
                 f"(EEP-matched; Bressan et al. 2012)")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=7, loc="lower left")
    return _fig_to_png(fig)


def plot_cosmology(distances: dict) -> bytes:
    z = np.asarray(distances["z"])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].plot(z, distances["comoving_distance_Mpc"], label="comoving D_C")
    axes[0].plot(z, distances["luminosity_distance_Mpc"], label="luminosity D_L")
    axes[0].plot(z, distances["angular_diameter_distance_Mpc"], label="angular D_A")
    axes[0].set_xlabel("redshift z")
    axes[0].set_ylabel("distance [Mpc]")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)
    axes[0].set_title("Distance–redshift relations")
    axes[1].plot(z, distances["age_Gyr"], color="#aed581")
    axes[1].set_xlabel("redshift z")
    axes[1].set_ylabel("age of universe [Gyr]")
    axes[1].grid(alpha=0.3)
    axes[1].set_title("Cosmic age vs redshift")
    return _fig_to_png(fig)


def plot_posterior(posterior: dict) -> bytes:
    samples = np.asarray(posterior.get("samples", []))
    fig, ax = plt.subplots(figsize=(6, 5))
    if samples.size:
        ax.scatter(samples[:, 0], samples[:, 1], s=3, alpha=0.25, c="#ba68c8")
    ax.set_xlabel("H₀ [km/s/Mpc]")
    ax.set_ylabel("Ω_m")
    ax.set_title("MCMC posterior (emcee)")
    ax.grid(alpha=0.3)
    return _fig_to_png(fig)
