import { useState } from "react";
import { api } from "../api";
import Plot from "../components/Plot";

interface Distances {
  z: number[];
  comoving_distance_Mpc: number[];
  luminosity_distance_Mpc: number[];
  angular_diameter_distance_Mpc: number[];
  age_Gyr: number[];
  H0_km_s_Mpc: number;
  Om0: number;
  Ol0: number;
}
interface Friedmann {
  E_z: number;
  H_z_km_s_Mpc: number;
  Omega_m_z: number;
  Omega_Lambda: number;
  equation: string;
}
interface Posterior {
  is_demo_data: boolean;
  data_provenance: string;
  H0_median: number;
  H0_ci68: number[];
  Om0_median: number;
  Om0_ci68: number[];
  acceptance_fraction: number;
  samples: number[][];
}

export default function CosmologyLab() {
  const [H0, setH0] = useState(67.4);
  const [Om0, setOm0] = useState(0.315);
  const [zMax, setZMax] = useState(2.0);
  const [dist, setDist] = useState<Distances | null>(null);
  const [fried, setFried] = useState<Friedmann | null>(null);
  const [posterior, setPosterior] = useState<Posterior | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mcmcBusy, setMcmcBusy] = useState(false);

  async function compute() {
    setBusy(true);
    setError("");
    try {
      const resp = await api<{ distances: Distances; friedmann: Friedmann }>("/api/labs/cosmology", {
        method: "POST",
        body: JSON.stringify({ H0, Om0, z_max: zMax }),
      });
      setDist(resp.distances);
      setFried(resp.friedmann);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runMcmc() {
    setMcmcBusy(true);
    setError("");
    try {
      const resp = await api<{ posterior: Posterior }>("/api/labs/cosmology/mcmc", {
        method: "POST",
        body: JSON.stringify({ use_demo_data: true, n_steps: 1500 }),
      });
      setPosterior(resp.posterior);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setMcmcBusy(false);
    }
  }

  const distTraces = dist
    ? [
        { x: dist.z, y: dist.comoving_distance_Mpc, mode: "lines", name: "comoving D_C", line: { color: "#4fc3f7" } },
        { x: dist.z, y: dist.luminosity_distance_Mpc, mode: "lines", name: "luminosity D_L", line: { color: "#ff8a65" } },
        { x: dist.z, y: dist.angular_diameter_distance_Mpc, mode: "lines", name: "angular D_A", line: { color: "#aed581" } },
      ]
    : [];

  const ageTrace = dist
    ? [{ x: dist.z, y: dist.age_Gyr, mode: "lines", name: "age [Gyr]", line: { color: "#ba68c8" }, fill: "tozeroy" }]
    : [];

  const postTrace = posterior
    ? [
        {
          x: posterior.samples.map((s) => s[0]),
          y: posterior.samples.map((s) => s[1]),
          mode: "markers",
          marker: { size: 3, color: "#ba68c8", opacity: 0.35 },
          name: "posterior samples",
        },
      ]
    : [];

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold text-slate-100">Cosmology Laboratory</h1>
        <p className="text-sm text-slate-400">
          Flat ΛCDM expansion with Astropy; posterior estimation with emcee and explicit
          uncertainty quantification.
        </p>
      </header>

      <section className="card flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-400">
          H₀ [km/s/Mpc]
          <input className="input mt-1 w-32" type="number" step="0.1" value={H0}
            onChange={(e) => setH0(Number(e.target.value))} />
        </label>
        <label className="text-xs text-slate-400">
          Ω_m
          <input className="input mt-1 w-32" type="number" step="0.01" value={Om0}
            onChange={(e) => setOm0(Number(e.target.value))} />
        </label>
        <label className="text-xs text-slate-400">
          z_max
          <input className="input mt-1 w-28" type="number" step="0.1" value={zMax}
            onChange={(e) => setZMax(Number(e.target.value))} />
        </label>
        <button className="btn-primary" onClick={() => void compute()} disabled={busy}>
          {busy ? "Computing…" : "Compute distance ladder"}
        </button>
        <button className="btn-ghost" onClick={() => void runMcmc()} disabled={mcmcBusy}>
          {mcmcBusy ? "Sampling (30s)…" : "Run H₀/Ω_m posterior (emcee)"}
        </button>
        {error && <span className="text-xs text-rose-400">{error}</span>}
      </section>

      {posterior && (
        <div className="rounded-xl border border-amber-700/60 bg-amber-500/10 p-3 text-xs text-amber-200">
          ⚠ The MCMC used <b>synthetic demo data</b> generated from Planck18 with noise —{" "}
          {posterior.data_provenance}. It is <b>not</b> a fit to real supernova observations.
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card">
          <h2 className="mb-2 font-semibold text-slate-200">Distance–redshift relations</h2>
          {dist ? (
            <Plot
              data={distTraces}
              layout={{
                xaxis: { title: "redshift z", gridcolor: "#1e293b" },
                yaxis: { title: "distance [Mpc]", gridcolor: "#1e293b" },
                title: `H₀=${dist.H0_km_s_Mpc}, Ω_m=${dist.Om0}, Ω_Λ=${dist.Ol0.toFixed(3)}`,
              }}
            />
          ) : (
            <p className="text-sm text-slate-500">Compute to plot comoving/luminosity/angular distances.</p>
          )}
        </section>

        <section className="card">
          <h2 className="mb-2 font-semibold text-slate-200">Cosmic age vs redshift</h2>
          {dist ? (
            <Plot
              data={ageTrace}
              layout={{
                xaxis: { title: "redshift z", gridcolor: "#1e293b" },
                yaxis: { title: "age [Gyr]", gridcolor: "#1e293b" },
                title: `age at z=0: ${dist.age_Gyr[0].toFixed(2)} Gyr`,
              }}
            />
          ) : (
            <p className="text-sm text-slate-500">Compute to plot the expansion history.</p>
          )}
        </section>

        <section className="card">
          <h2 className="mb-2 font-semibold text-slate-200">Friedmann terms at z = {zMax}</h2>
          {fried ? (
            <div className="space-y-2 text-sm text-slate-300">
              <div className="mono text-xs text-cyan-300">{fried.equation}</div>
              <div className="grid grid-cols-2 gap-2">
                <div>Ω_m(z): <span className="mono">{fried.Omega_m_z.toFixed(4)}</span></div>
                <div>Ω_Λ: <span className="mono">{fried.Omega_Lambda.toFixed(4)}</span></div>
                <div>E(z): <span className="mono">{fried.E_z.toFixed(4)}</span></div>
                <div>H(z): <span className="mono">{fried.H_z_km_s_Mpc.toFixed(2)} km/s/Mpc</span></div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Compute to see the Friedmann equation terms.</p>
          )}
        </section>

        <section className="card">
          <h2 className="mb-2 font-semibold text-slate-200">
            Parameter posterior (UQ) <span className="text-xs font-normal text-amber-400">demo data</span>
          </h2>
          {posterior ? (
            <>
              <Plot data={postTrace} layout={{
                xaxis: { title: "H₀ [km/s/Mpc]", gridcolor: "#1e293b" },
                yaxis: { title: "Ω_m", gridcolor: "#1e293b" },
                title: `acceptance=${posterior.acceptance_fraction.toFixed(2)}`,
              }} height={300} />
              <div className="mt-2 grid grid-cols-2 gap-2 text-sm text-slate-300">
                <div>H₀ = <span className="mono text-cyan-300">{posterior.H0_median.toFixed(2)}</span>{" "}
                  [{posterior.H0_ci68[0].toFixed(2)}, {posterior.H0_ci68[1].toFixed(2)}] (68%)</div>
                <div>Ω_m = <span className="mono text-orange-300">{posterior.Om0_median.toFixed(3)}</span>{" "}
                  [{posterior.Om0_ci68[0].toFixed(3)}, {posterior.Om0_ci68[1].toFixed(3)}] (68%)</div>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-500">Run the sampler to see credible intervals.</p>
          )}
        </section>
      </div>
    </div>
  );
}