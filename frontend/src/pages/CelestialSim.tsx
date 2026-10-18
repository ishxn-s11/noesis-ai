import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, getToken } from "../api";
import Plot from "../components/Plot";

interface BodyRow {
  name: string;
  mass_value: number;
  mass_unit: "msun" | "kg" | "mjup" | "mearth";
  a?: number;
  e?: number;
  inc?: number;
  x?: number;
  y?: number;
  z?: number;
  vx?: number;
  vy?: number;
  vz?: number;
}

interface SimResult {
  status: string;
  diagnostics: {
    energy_drift_rel_max: number;
    angmom_drift_rel_max: number;
    energy_rel_series: number[];
    angmom_rel_series: number[];
    min_pairwise_distance_au: number | null;
  };
  analytics: { pair_periods: Array<{ pair: string; kepler_period_yr: number }> };
  meta: { integrator: string; t_end: number; n_snapshots: number; wall_time_s: number };
  snapshots: { time_yr: number[]; bodies: Record<string, { x: number[]; y: number[]; z: number[] }> };
}

const DEFAULT_BODIES: BodyRow[] = [
  { name: "star", mass_value: 1, mass_unit: "msun", x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: 0 },
  { name: "planet", mass_value: 1e-3, mass_unit: "msun", a: 1, e: 0.02 },
  { name: "perturber", mass_value: 0.02, mass_unit: "msun", a: 2.5, e: 0.3, inc: 0 },
];

export default function CelestialSim() {
  const [bodies, setBodies] = useState<BodyRow[]>(DEFAULT_BODIES);
  const [integrator, setIntegrator] = useState("ias15");
  const [tEnd, setTEnd] = useState(50);
  const [dt, setDt] = useState(0.01);
  const [jobId, setJobId] = useState("");
  const [error, setError] = useState("");
  const [view, setView] = useState<"xy" | "xz">("xy");

  const result = useQuery({
    queryKey: ["sim", jobId],
    queryFn: () => api<{ status: string; result: SimResult | null }>(`/api/simulations/${jobId}/result`),
    enabled: Boolean(jobId),
    refetchInterval: (q) => {
      const st = q.state.data?.status;
      return st === "queued" || st === "running" ? 1000 : false;
    },
  });

  function updateBody(i: number, patch: Partial<BodyRow>) {
    setBodies((prev) => prev.map((b, idx) => (idx === i ? { ...b, ...patch } : b)));
  }

  async function run() {
    setError("");
    try {
      const resp = await api<{ job_id: string }>("/api/simulations", {
        method: "POST",
        body: JSON.stringify({
          request: {
            bodies: bodies.map((b) => ({ ...b, inc: b.inc ?? 0 })),
            config: { integrator, dt, t_end: tEnd, output_every: 50, exit_unstable: true },
          },
        }),
      });
      setJobId(resp.job_id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const data = result.data?.result;
  const finished = result.data?.status === "succeeded" && data;

  const trajData = (() => {
    if (!data) return [];
    const names = Object.keys(data.snapshots.bodies);
    return names.map((n, i) => {
      const b = data.snapshots.bodies[n];
      const colors = ["#4fc3f7", "#ff8a65", "#aed581", "#ba68c8", "#f06292", "#ffd54f"];
      return {
        x: view === "xy" ? b.x : b.x,
        y: view === "xy" ? b.y : b.z,
        mode: "lines",
        name: n,
        line: { color: colors[i % colors.length], width: 1.4 },
      };
    });
  })();

  const driftData = data
    ? [
        {
          x: data.snapshots.time_yr,
          y: data.diagnostics.energy_rel_series,
          mode: "lines",
          name: "ΔE/E₀",
          line: { color: "#4fc3f7" },
        },
        {
          x: data.snapshots.time_yr,
          y: data.diagnostics.angmom_rel_series,
          mode: "lines",
          name: "ΔL/L₀",
          line: { color: "#ff8a65" },
        },
      ]
    : [];

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold text-slate-100">Celestial Mechanics Simulator</h1>
        <p className="text-sm text-slate-400">
          Real REBOUND N-body integrations with conservation diagnostics.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-[420px_1fr]">
        <div className="space-y-4">
          <section className="card">
            <h2 className="mb-2 font-semibold text-slate-200">Bodies</h2>
            <div className="space-y-3">
              {bodies.map((b, i) => (
                <div key={i} className="rounded-lg border border-slate-800 p-2">
                  <div className="flex gap-2">
                    <input
                      className="input"
                      value={b.name}
                      onChange={(e) => updateBody(i, { name: e.target.value })}
                    />
                    <input
                      className="input w-24"
                      type="number"
                      step="any"
                      value={b.mass_value}
                      onChange={(e) => updateBody(i, { mass_value: Number(e.target.value) })}
                    />
                    <select
                      className="input w-24"
                      value={b.mass_unit}
                      onChange={(e) => updateBody(i, { mass_unit: e.target.value as BodyRow["mass_unit"] })}
                    >
                      <option value="msun">M☉</option>
                      <option value="mjup">M♃</option>
                      <option value="mearth">M⊕</option>
                      <option value="kg">kg</option>
                    </select>
                  </div>
                  <div className="mt-2 flex gap-2">
                    <label className="flex-1 text-[10px] text-slate-500">
                      a [AU]
                      <input
                        className="input py-1"
                        type="number"
                        step="any"
                        placeholder="cartesian"
                        value={b.a ?? ""}
                        onChange={(e) =>
                          updateBody(i, { a: e.target.value === "" ? undefined : Number(e.target.value) })
                        }
                      />
                    </label>
                    <label className="flex-1 text-[10px] text-slate-500">
                      e
                      <input
                        className="input py-1"
                        type="number"
                        step="any"
                        value={b.e ?? ""}
                        onChange={(e) =>
                          updateBody(i, { e: e.target.value === "" ? undefined : Number(e.target.value) })
                        }
                      />
                    </label>
                    <label className="flex-1 text-[10px] text-slate-500">
                      i [rad]
                      <input
                        className="input py-1"
                        type="number"
                        step="any"
                        value={b.inc ?? ""}
                        onChange={(e) =>
                          updateBody(i, { inc: e.target.value === "" ? undefined : Number(e.target.value) })
                        }
                      />
                    </label>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="card space-y-3">
            <h2 className="font-semibold text-slate-200">Integrator</h2>
            <div className="grid grid-cols-3 gap-2">
              <label className="text-xs text-slate-400">
                method
                <select className="input mt-1" value={integrator} onChange={(e) => setIntegrator(e.target.value)}>
                  <option value="ias15">IAS15</option>
                  <option value="whfast">WHFast</option>
                  <option value="mercurius">Mercurius</option>
                  <option value="rk4">RK4</option>
                  <option value="euler">Euler</option>
                </select>
              </label>
              <label className="text-xs text-slate-400">
                t_end [yr]
                <input className="input mt-1" type="number" step="any" value={tEnd}
                  onChange={(e) => setTEnd(Number(e.target.value))} />
              </label>
              <label className="text-xs text-slate-400">
                dt [yr]
                <input className="input mt-1" type="number" step="any" value={dt}
                  onChange={(e) => setDt(Number(e.target.value))} />
              </label>
            </div>
            <button className="btn-primary w-full justify-center" onClick={run}>
              ▶ Execute N-body integration
            </button>
            {error && <div className="text-xs text-rose-400">{error}</div>}
            {jobId && (
              <div className="mono text-[11px] text-slate-500">
                job {jobId.slice(0, 8)} · {result.data?.status ?? "…"}
              </div>
            )}
          </section>
        </div>

        <div className="space-y-4">
          {finished && data && (
            <>
              <section className="card">
                <div className="mb-2 flex items-center justify-between">
                  <h2 className="font-semibold text-slate-200">Trajectories</h2>
                  <div className="flex gap-1">
                    {(["xy", "xz"] as const).map((m) => (
                      <button key={m} className={view === m ? "btn-primary text-xs" : "btn-ghost text-xs"}
                        onClick={() => setView(m)}>
                        {m === "xy" ? "sky plane (x,y)" : "inclination (x,z)"}
                      </button>
                    ))}
                  </div>
                </div>
                <Plot
                  data={trajData}
                  layout={{
                    title: `Integrator: ${data.meta.integrator}, t_end=${data.meta.t_end} yr`,
                    xaxis: { title: "x [AU]", gridcolor: "#1e293b" },
                    yaxis: { title: view === "xy" ? "y [AU]" : "z [AU]", gridcolor: "#1e293b", scaleanchor: view === "xy" ? "x" : undefined },
                  }}
                  height={430}
                />
              </section>

              <section className="grid gap-4 md:grid-cols-3">
                <div className="card">
                  <div className="text-xs uppercase text-slate-500">Status</div>
                  <div className={`mt-1 text-xl font-semibold ${data.status === "completed" ? "text-emerald-300" : "text-amber-300"}`}>
                    {data.status}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {data.meta.n_snapshots} snapshots · {data.meta.wall_time_s}s wall
                  </div>
                </div>
                <div className="card">
                  <div className="text-xs uppercase text-slate-500">max |ΔE/E₀|</div>
                  <div className="mono mt-1 text-xl font-semibold text-cyan-300">
                    {data.diagnostics.energy_drift_rel_max.toExponential(2)}
                  </div>
                </div>
                <div className="card">
                  <div className="text-xs uppercase text-slate-500">max |ΔL/L₀|</div>
                  <div className="mono mt-1 text-xl font-semibold text-orange-300">
                    {data.diagnostics.angmom_drift_rel_max.toExponential(2)}
                  </div>
                </div>
              </section>

              <section className="card">
                <h2 className="mb-2 font-semibold text-slate-200">Conservation diagnostics</h2>
                <Plot
                  data={driftData}
                  layout={{
                    xaxis: { title: "time [yr]", gridcolor: "#1e293b" },
                    yaxis: { title: "relative drift", type: "log", gridcolor: "#1e293b" },
                  }}
                  height={300}
                />
                {data.analytics.pair_periods.length > 0 && (
                  <div className="mt-2 text-xs text-slate-400">
                    Kepler period check: {data.analytics.pair_periods[0].pair} → P ={" "}
                    <span className="mono text-cyan-300">
                      {data.analytics.pair_periods[0].kepler_period_yr.toFixed(4)} yr
                    </span>{" "}
                    (analytic P² = a³/M)
                  </div>
                )}
              </section>
            </>
          )}

          {!finished && (
            <section className="card text-sm text-slate-500">
              Configure bodies and execute to see trajectories, energy/angular-momentum
              conservation and Kepler cross-checks. Jobs run in an isolated subprocess with a
              wall-clock deadline.
            </section>
          )}
        </div>
      </div>
    </div>
  );
}