import { useState } from "react";
import { api, apiUrl, getToken } from "../api";

interface ArchiveResult {
  source?: string;
  source_url?: string;
  n_rows?: number;
  rows?: unknown[][];
  columns?: string[];
  papers?: Array<{ title: string; id: string; published: string; authors: string[] }>;
  resolver_data?: Record<string, string>;
  raw_xml_excerpt?: string;
  execution_time_s?: number;
  message?: string;
}

const ARCHIVES = [
  { id: "exoplanet_archive", label: "NASA Exoplanet Archive (TAP/ADQL)" },
  { id: "gaia", label: "ESA Gaia DR3 cone search (TAP)" },
  { id: "vizier", label: "VizieR catalog (TAP)" },
  { id: "simbad", label: "SIMBAD name resolver" },
  { id: "arxiv", label: "arXiv literature search" },
];

export default function ObservationExplorer() {
  const [archive, setArchive] = useState("exoplanet_archive");
  const [params, setParams] = useState('{"max_rows": 25}');
  const [result, setResult] = useState<ArchiveResult | null>(null);
  const [transform, setTransform] = useState<Record<string, unknown> | null>(null);
  const [coords, setCoords] = useState({ ra: 266.4168, dec: -29.0078 });
  const [lightcurve, setLightcurve] = useState("");
  const [lcStats, setLcStats] = useState<Record<string, unknown> | null>(null);
  const [fitsInfo, setFitsInfo] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function query() {
    setBusy(true);
    setError("");
    try {
      const resp = await api<ArchiveResult>("/api/labs/archive", {
        method: "POST",
        body: JSON.stringify({ archive, params: JSON.parse(params) }),
      });
      setResult(resp);
    } catch (err) {
      setResult(null);
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function transformCoords() {
    setError("");
    try {
      const out = await api<Record<string, unknown>>("/api/labs/transform", {
        method: "POST",
        body: JSON.stringify({ ra: coords.ra, dec: coords.dec, to: "galactic" }),
      });
      setTransform(out);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function analyzeLightcurve() {
    setError("");
    try {
      const parsed = JSON.parse(lightcurve) as { times: number[]; mags: number[] };
      const stats = await api<Record<string, unknown>>("/api/labs/lightcurve", {
        method: "POST",
        body: JSON.stringify(parsed),
      });
      setLcStats(stats);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function uploadFits(file: File) {
    setError("");
    const form = new FormData();
    form.append("file", file);
    try {
      const resp = await fetch(apiUrl("/api/labs/fits"), {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken() ?? ""}` },
        body: form,
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.message ?? `HTTP ${resp.status}`);
      setFitsInfo(body.inspection as Record<string, unknown>);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold text-slate-100">Observation Explorer</h1>
        <p className="text-sm text-slate-400">
          Real archive queries through documented APIs — failures surface as errors, never as
          fabricated data.
        </p>
      </header>

      <section className="card space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-slate-400">
            Archive
            <select className="input mt-1 w-72" value={archive} onChange={(e) => {
              setArchive(e.target.value);
              setParams(
                e.target.value === "gaia"
                  ? '{"ra_deg": 101.287, "dec_deg": -16.716, "radius_arcsec": 30, "max_rows": 25}'
                  : e.target.value === "vizier"
                    ? '{"catalog": "I/239/hip_main", "max_rows": 25}'
                    : e.target.value === "simbad"
                      ? '{"object_name": "Vega"}'
                      : e.target.value === "arxiv"
                        ? '{"query": "exoplanet transit photometry", "max_results": 3}'
                        : '{"where": "defaultflag=1", "max_rows": 25}',
              );
            }}>
              {ARCHIVES.map((a) => (
                <option key={a.id} value={a.id}>{a.label}</option>
              ))}
            </select>
          </label>
          <label className="flex-1 text-xs text-slate-400">
            Query params (JSON)
            <input className="input mt-1 mono" value={params} onChange={(e) => setParams(e.target.value)} />
          </label>
          <button className="btn-primary" onClick={() => void query()} disabled={busy}>
            {busy ? "Querying…" : "Query archive"}
          </button>
        </div>
        {error && <div className="text-xs text-rose-400">{error}</div>}
        {result && (
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
              {result.source && <span className="badge bg-cyan-500/15 text-cyan-300">{result.source}</span>}
              {result.execution_time_s !== undefined && <span>{result.execution_time_s}s</span>}
              {result.n_rows !== undefined && <span>{result.n_rows} rows</span>}
            </div>
            {result.papers && (
              <ul className="space-y-2">
                {result.papers.map((p) => (
                  <li key={p.id} className="text-xs">
                    <a className="text-cyan-400 hover:underline" href={p.id} target="_blank" rel="noreferrer">
                      {p.title}
                    </a>
                    <div className="text-slate-500">
                      {p.published?.slice(0, 10)} · {p.authors.slice(0, 3).join(", ")}
                      {p.authors.length > 3 ? " et al." : ""}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {result.resolver_data && (
              <pre className="mono text-[11px] text-slate-300">{JSON.stringify(result.resolver_data, null, 2)}</pre>
            )}
            {result.rows && result.rows.length > 0 && (
              <div className="max-h-72 overflow-auto">
                <table className="w-full text-left text-[11px]">
                  <thead className="sticky top-0 bg-slate-900 text-slate-500">
                    <tr>{(result.columns ?? []).map((c) => <th key={c} className="px-1 py-1">{c}</th>)}</tr>
                  </thead>
                  <tbody className="text-slate-300">
                    {result.rows.slice(0, 25).map((row, i) => (
                      <tr key={i} className="border-t border-slate-800/70">
                        {row.map((cell, j) => (
                          <td key={j} className="px-1 py-0.5 mono">{String(cell ?? "—")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card space-y-3">
          <h2 className="font-semibold text-slate-200">Coordinates &amp; cross-match</h2>
          <div className="flex gap-2">
            <label className="flex-1 text-xs text-slate-400">
              RA [deg]
              <input className="input mt-1" type="number" step="any" value={coords.ra}
                onChange={(e) => setCoords({ ...coords, ra: Number(e.target.value) })} />
            </label>
            <label className="flex-1 text-xs text-slate-400">
              Dec [deg]
              <input className="input mt-1" type="number" step="any" value={coords.dec}
                onChange={(e) => setCoords({ ...coords, dec: Number(e.target.value) })} />
            </label>
            <button className="btn-ghost self-end" onClick={() => void transformCoords()}>
              Transform → galactic
            </button>
          </div>
          {transform && (
            <pre className="mono text-[11px] text-slate-300">{JSON.stringify(transform, null, 2)}</pre>
          )}
          <p className="text-[11px] text-slate-500">
            Defaults: Sgr A* J2000 (266.4168, −29.0078) → galactic (359.9443, −0.0462). Round-trip
            accuracy verified by the Validation Agent.
          </p>
        </section>

        <section className="card space-y-3">
          <h2 className="font-semibold text-slate-200">FITS inspection</h2>
          <input
            type="file"
            accept=".fits,.fit,.fts"
            className="block w-full text-xs text-slate-400 file:btn-ghost file:mr-3"
            onChange={(e) => e.target.files?.[0] && void uploadFits(e.target.files[0])}
          />
          {fitsInfo && (
            <pre className="mono max-h-64 overflow-auto text-[11px] text-slate-300">
              {JSON.stringify(fitsInfo, null, 2).slice(0, 4000)}
            </pre>
          )}
        </section>

        <section className="card space-y-3 lg:col-span-2">
          <h2 className="font-semibold text-slate-200">Light-curve time-series analysis</h2>
          <p className="text-xs text-slate-500">
            Paste JSON <span className="mono">{"{\"times\": [...], \"mags\": [...]}"}</span> — Lomb-Scargle
            periodogram runs server-side (scipy).
          </p>
          <textarea
            className="input h-24 mono text-xs"
            placeholder='{"times": [0, 1, 2, ...], "mags": [12.1, 12.3, ...]}'
            value={lightcurve}
            onChange={(e) => setLightcurve(e.target.value)}
          />
          <button className="btn-primary" onClick={() => void analyzeLightcurve()}>
            Analyze light curve
          </button>
          {lcStats && (
            <div className="grid grid-cols-2 gap-2 text-sm text-slate-300 md:grid-cols-5">
              <div>points: <span className="mono">{String(lcStats.n_points)}</span></div>
              <div>best period: <span className="mono text-cyan-300">{Number(lcStats.best_period_days).toFixed(4)} d</span></div>
              <div>power: <span className="mono">{Number(lcStats.periodogram_power_max).toFixed(3)}</span></div>
              <div>mag mean: <span className="mono">{Number(lcStats.mag_mean).toFixed(3)}</span></div>
              <div>σ: <span className="mono">{Number(lcStats.mag_std).toFixed(3)}</span></div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
