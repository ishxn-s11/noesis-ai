import { useEffect, useState } from "react";
import { api, downloadArtifact } from "../api";
import Plot from "../components/Plot";
import { ExplainText } from "../components/Explain";
import { chartColors, useTheme } from "../theme";

interface TrackCurve {
  grid_mass_msun: number;
  label: string;
  log_teff: number[];
  log_lum: number[];
  metallicity_z?: number;
  zams?: { log_teff: number; log_lum: number };
  ms_end?: { log_teff: number; log_lum: number };
}
interface GridInfo {
  helium_y: number;
  n_rows: number;
  n_tracks: number;
  provenance_file: string;
  downloaded_utc: string;
}
interface Provenance {
  dataset: string;
  source_page: string;
  source_release: string;
  metallicity_z: number;
  metallicities_z?: number[];
  grids?: Record<string, GridInfo>;
  citations: string[];
  grid?: { n_tracks: number; mass_range_msun: number[]; interpolation: string };
  derived_columns?: Record<string, string>;
}
interface StellarParams {
  model_fidelity: string;
  assumptions: string[];
  mass_msun: number;
  luminosity_msun: number;
  radius_msun: number;
  teff_K: number;
  spectral_class: string;
  ms_lifetime_Gyr?: number;
  ms_lifetime_Gyr_proxy?: number;
  expected_remnant?: string;
  references: string[];
  age_yr?: number;
  metallicity_z?: number;
  zams_age_yr?: number;
  ms_end_age_yr_proxy?: number;
  provenance?: Provenance;
  track?: TrackCurve;
}
interface RefStar {
  name: string;
  mass_msun: number;
  teff_K: number;
  lum_msun: number;
  source: string;
}
interface BrowserResponse {
  metallicity_z: number;
  metallicities_z: number[];
  n_tracks: number;
  tracks: TrackCurve[];
  provenance: Provenance;
}
interface IsochronePoint {
  mass_msun: number;
  log_teff: number;
  log_lum: number;
}
interface IsochroneResponse {
  age_yr: number;
  metallicity_z: number;
  derivation: string;
  n_points: number;
  n_tracks_total: number;
  excluded_masses_msun: number[];
  points: IsochronePoint[];
}

/** Available metallicities: two bundled PARSEC grids + interpolated picks. */
const Z_OPTIONS = [0.001, 0.002, 0.004, 0.008, 0.014];
const GRID_Z = new Set([0.001, 0.014]);

/** Preset isochrone ages; each omits the masses whose tracks end earlier. */
const ISO_AGE_PRESETS = [
  { age_yr: 1e6, label: "1 Myr" },
  { age_yr: 1e7, label: "10 Myr" },
  { age_yr: 1e8, label: "100 Myr" },
  { age_yr: 1e9, label: "1 Gyr" },
  { age_yr: 1e10, label: "10 Gyr" },
];
/** Distinct dashed-overlay colors, legible on both themes. */
const ISO_COLORS = ["#ffd54f", "#4fc3f7", "#aed581", "#ba68c8", "#f06292"];

/** Track color: blue (0.1 Msun) -> orange (100 Msun) by log mass. */
function massColor(m: number): string {
  const t = Math.min(
    1,
    Math.max(0, (Math.log10(m) - Math.log10(0.1)) / (Math.log10(100) - Math.log10(0.1))),
  );
  const lerp = (a: number, b: number) => Math.round(a + (b - a) * t);
  return `rgb(${lerp(0x4f, 0xff)},${lerp(0xc3, 0x8a)},${lerp(0xf7, 0x65)})`;
}

export default function StellarLab() {
  const [view, setView] = useState<"star" | "tracks">("star");
  const [mass, setMass] = useState(1.0);
  const [source, setSource] = useState<"analytic" | "parsec">("parsec");
  const [metallicity, setMetallicity] = useState(0.014);
  const [ageGyr, setAgeGyr] = useState<string>("");
  const [result, setResult] = useState<{ parameters: StellarParams; reference_stars: RefStar[] } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [browser, setBrowser] = useState<BrowserResponse | null>(null);
  const [browserBusy, setBrowserBusy] = useState(false);
  const [browserError, setBrowserError] = useState("");
  const [pngBusy, setPngBusy] = useState(false);
  const [isoAges, setIsoAges] = useState<number[]>([1e9, 1e10]);
  const [isoCache, setIsoCache] = useState<Record<string, IsochroneResponse | { error: string }>>({});
  const [isoBusy, setIsoBusy] = useState(false);

  async function exportPng() {
    setPngBusy(true);
    setBrowserError("");
    try {
      const resp = await api<{ plot_artifact: { id: string; filename: string } }>(
        `/api/labs/stellar/tracks.png?metallicity_z=${metallicity}`,
        { method: "POST" },
      );
      downloadArtifact(resp.plot_artifact.id, resp.plot_artifact.filename);
    } catch (err) {
      setBrowserError((err as Error).message);
    } finally {
      setPngBusy(false);
    }
  }

  async function compute(target?: number, src?: "analytic" | "parsec", z?: number) {
    const m = target ?? mass;
    const s = src ?? source;
    const zz = z ?? metallicity;
    setBusy(true);
    setError("");
    try {
      const body: Record<string, unknown> = { mass_msun: m, source: s };
      const age = Number(ageGyr);
      if (s === "parsec" && ageGyr !== "" && Number.isFinite(age) && age > 0) {
        body.age_yr = age * 1e9;
      }
      if (s === "parsec") body.metallicity_z = zz;
      const resp = await api<{ parameters: StellarParams; reference_stars: RefStar[] }>(
        "/api/labs/stellar",
        { method: "POST", body: JSON.stringify(body) },
      );
      setResult(resp);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // Track browser: (re)load the full grid whenever the view or Z changes
  useEffect(() => {
    if (view !== "tracks") return;
    let cancelled = false;
    setBrowserBusy(true);
    setBrowserError("");
    api<BrowserResponse>(`/api/labs/stellar/tracks?metallicity_z=${metallicity}`)
      .then((b) => {
        if (!cancelled) setBrowser(b);
      })
      .catch((err: Error) => {
        if (!cancelled) setBrowserError(err.message);
      })
      .finally(() => {
        if (!cancelled) setBrowserBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [view, metallicity]);

  // Isochrones: fetch any selected age not already cached for this Z
  useEffect(() => {
    if (view !== "tracks") return;
    const missing = isoAges.filter((a) => !isoCache[`${metallicity}|${a}`]);
    if (missing.length === 0) return;
    let cancelled = false;
    setIsoBusy(true);
    void Promise.all(
      missing.map(async (a) => {
        const key = `${metallicity}|${a}`;
        try {
          const iso = await api<IsochroneResponse>(
            `/api/labs/stellar/isochrone?age_yr=${a}&metallicity_z=${metallicity}`,
          );
          return [key, iso as IsochroneResponse | { error: string }] as const;
        } catch (err) {
          return [key, { error: (err as Error).message }] as const;
        }
      }),
    ).then((entries) => {
      if (!cancelled) {
        setIsoCache((prev) => ({ ...prev, ...Object.fromEntries(entries) }));
        setIsoBusy(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [view, metallicity, isoAges, isoCache]);

  const p = result?.parameters;
  const refs = result?.reference_stars ?? [];
  const prov = p?.provenance ?? browser?.provenance;
  // useTheme() subscribes this page to the toggle: it re-renders (literal
  // Plotly colors update) while keeping all component state mounted.
  const c = chartColors(useTheme());
  // show the Z actually evaluated, not the dataset default record
  const evalZ = (view === "star" ? p?.metallicity_z : browser?.metallicity_z)
    ?? prov?.metallicity_z;

  const hrData = [
    ...(p?.track
      ? [{
          x: p.track.log_teff.map((lt) => 10 ** lt),
          y: p.track.log_lum.map((ll) => 10 ** ll),
          mode: "lines" as const,
          name: p.track.label,
          line: { color: c.ink, width: 1.5 },
        }]
      : []),
    {
      x: [p?.teff_K ?? 0],
      y: [p?.luminosity_msun ?? 0],
      mode: "markers",
      name: "computed model",
      marker: { size: 14, color: c.ink, symbol: "circle" },
      text: p ? [`${p.mass_msun} M☉ (${p.spectral_class})`] : [""],
    },
    {
      x: refs.map((r) => r.teff_K),
      y: refs.map((r) => r.lum_msun),
      mode: "markers+text",
      name: "literature references",
      marker: { size: 13, color: "#ffd54f", symbol: "star" },
      text: refs.map((r) => r.name),
      textposition: "top right",
      textfont: { size: 9, color: c.muted },
    },
  ];

  // Dashed isochrone overlays. Each hover names its age and lists the masses
  // omitted because their tracks do not span that age (never extrapolated).
  const isoTraces: Array<Record<string, unknown>> = [];
  const isoFootnotes: string[] = [];
  isoAges.forEach((a, i) => {
    const entry = isoCache[`${metallicity}|${a}`];
    const label = ISO_AGE_PRESETS.find((p) => p.age_yr === a)?.label ?? `${a} yr`;
    if (!entry) return;
    if ("error" in entry) {
      isoFootnotes.push(`${label}: unavailable (${entry.error})`);
      return;
    }
    const color = ISO_COLORS[i % ISO_COLORS.length];
    const excluded = entry.excluded_masses_msun;
    const excNote = excluded.length
      ? `excluded masses: ${excluded.join(", ")} M☉ (tracks do not span this age)`
      : "excluded masses: none (the full grid spans this age)";
    isoFootnotes.push(
      excluded.length
        ? `${label}: ${entry.n_points} of ${entry.n_tracks_total} masses — omitted ${excluded.join(", ")} M☉`
        : `${label}: all ${entry.n_tracks_total} grid masses`,
    );
    isoTraces.push({
      x: entry.points.map((p) => 10 ** p.log_teff),
      y: entry.points.map((p) => 10 ** p.log_lum),
      mode: "lines+text",
      name: `Isochrone ${label}`,
      line: { color, width: 1.6, dash: "dash" },
      text: entry.points.map((p, j) => (j === entry.points.length - 1 ? label : "")),
      textposition: "bottom left",
      textfont: { size: 9, color },
      customdata: entry.points.map((p) => `M ${p.mass_msun} M☉`),
      hovertemplate:
        `%{customdata}<br>%{x:.4g} K, %{y:.4g} L☉<br>${excNote}` +
        `<extra>Isochrone ${label}</extra>`,
    });
  });

  const gridData = browser
    ? [
        ...browser.tracks.map((t) => ({
          x: t.log_teff.map((lt) => 10 ** lt),
          y: t.log_lum.map((ll) => 10 ** ll),
          mode: "lines" as const,
          name: t.label,
          line: { color: massColor(t.grid_mass_msun), width: 1.3 },
          hovertemplate: `${t.grid_mass_msun} M☉<extra></extra>`,
        })),
        {
          x: browser.tracks.map((t) => (t.zams ? 10 ** t.zams.log_teff : NaN)),
          y: browser.tracks.map((t) => (t.zams ? 10 ** t.zams.log_lum : NaN)),
          mode: "markers" as const,
          name: "ZAMS (proxy)",
          marker: { size: 4, color: "#94a3b8" },
          hovertemplate: "ZAMS<extra></extra>",
        },
        {
          x: browser.tracks.map((t) => (t.ms_end ? 10 ** t.ms_end.log_teff : NaN)),
          y: browser.tracks.map((t) => (t.ms_end ? 10 ** t.ms_end.log_lum : NaN)),
          mode: "markers" as const,
          name: "MS end (proxy)",
          marker: { size: 8, color: "#e2e8f0", symbol: "x-open" },
          hovertemplate: "MS end<extra></extra>",
        },
        {
          x: refs.map((r) => r.teff_K),
          y: refs.map((r) => r.lum_msun),
          mode: "markers+text",
          name: "literature references",
          marker: { size: 12, color: "#ffd54f", symbol: "star" },
          text: refs.map((r) => r.name),
          textposition: "top right",
          textfont: { size: 9, color: c.muted },
        },
        ...isoTraces,
      ]
    : [];

  const grid = Array.from({ length: 40 }, (_, i) => 0.2 + (i * 48) / 39);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold text-slate-100">Stellar Evolution Laboratory</h1>
        <p className="text-sm text-slate-400">
          <ExplainText
            text={
              "Published PARSEC v1.2S evolution tracks (Bressan et al. 2012) at Z = 0.014 and " +
              "Z = 0.001 with local interpolation (mass, age and metallicity), or simplified " +
              "analytic relations — each result labeled with its model fidelity and full provenance."
            }
          />
        </p>
      </header>

      <section className="card flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-400">
          View
          <div className="mt-1 flex gap-1">
            {(["star", "tracks"] as const).map((v) => (
              <button
                key={v}
                className={view === v ? "btn-primary text-xs" : "btn-ghost text-xs"}
                onClick={() => setView(v)}
              >
                {v === "star" ? "Single star" : "Track browser"}
              </button>
            ))}
          </div>
        </label>
        <label className="text-xs text-slate-400">
          Model source
          <div className="mt-1 flex gap-1">
            {(["parsec", "analytic"] as const).map((s) => (
              <button
                key={s}
                className={source === s ? "btn-primary text-xs" : "btn-ghost text-xs"}
                onClick={() => { setSource(s); void compute(undefined, s); }}
              >
                {s === "parsec" ? "PARSEC tracks" : "Analytic"}
              </button>
            ))}
          </div>
        </label>
        {view === "tracks" && (
          <label className="text-xs text-slate-400">
            Isochrones
            <div className="mt-1 flex gap-1">
              {ISO_AGE_PRESETS.map((p) => {
                const on = isoAges.includes(p.age_yr);
                return (
                  <button
                    key={p.age_yr}
                    className={on ? "btn-primary text-xs" : "btn-ghost text-xs"}
                    onClick={() =>
                      setIsoAges((prev) =>
                        prev.includes(p.age_yr)
                          ? prev.filter((x) => x !== p.age_yr)
                          : [...prev, p.age_yr],
                      )
                    }
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>
          </label>
        )}
        {(source === "parsec" || view === "tracks") && (
          <label className="text-xs text-slate-400">
            Metallicity Z
            <select
              className="input mt-1 w-44"
              value={metallicity}
              onChange={(e) => {
                const z = Number(e.target.value);
                setMetallicity(z);
                if (view === "star" && source === "parsec") void compute(undefined, undefined, z);
              }}
            >
              {Z_OPTIONS.map((z) => (
                <option key={z} value={z}>
                  {z} {GRID_Z.has(z) ? "(grid)" : "(interpolated)"}
                </option>
              ))}
            </select>
          </label>
        )}
        {view === "star" && (
          <>
            <label className="text-xs text-slate-400">
              Stellar mass [M☉]
              <input
                className="input mt-1 w-40"
                type="number"
                step="0.05"
                min={0.1}
                max={100}
                value={mass}
                onChange={(e) => setMass(Number(e.target.value))}
              />
            </label>
            {source === "parsec" && (
              <label className="text-xs text-slate-400">
                Age [Gyr] (blank = mid-MS)
                <input
                  className="input mt-1 w-40"
                  type="number"
                  step="0.1"
                  min={0.001}
                  placeholder="e.g. 4.6"
                  value={ageGyr}
                  onChange={(e) => setAgeGyr(e.target.value)}
                />
              </label>
            )}
            <button className="btn-primary" onClick={() => void compute()} disabled={busy}>
              {busy ? "Computing…" : "Compute stellar model"}
            </button>
            <div className="flex gap-1">
              {[0.1, 0.5, 1, 2, 10, 40].map((m) => (
                <button key={m} className="btn-ghost text-xs" onClick={() => { setMass(m); void compute(m); }}>
                  {m} M☉
                </button>
              ))}
            </div>
          </>
        )}
        {error && <span className="text-xs text-rose-400">{error}</span>}
        {browserError && <span className="text-xs text-rose-400">{browserError}</span>}
      </section>

      {view === "tracks" && (
        <section className="card">
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <h2 className="font-semibold text-slate-200">
              Evolutionary tracks — full grid{" "}
              {browser && <span className="text-sm font-normal text-slate-400">at Z = {browser.metallicity_z}</span>}
            </h2>
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-500">
                {browserBusy ? "Loading tracks…" : browser ? `${browser.n_tracks} published tracks` : ""}
                {isoBusy ? " · loading isochrones…" : ""}
              </span>
              <button
                className="btn-ghost text-xs"
                onClick={() => void exportPng()}
                disabled={pngBusy || !browser}
              >
                {pngBusy ? "Rendering…" : "Export PNG"}
              </button>
            </div>
          </div>
          <Plot
            data={gridData}
            layout={{
              xaxis: { title: "Teff [K]", type: "log", autorange: "reversed", gridcolor: c.grid },
              yaxis: { title: "L [L☉]", type: "log", gridcolor: c.grid },
              title: "PARSEC v1.2S — color: 0.1 M☉ (blue) → 100 M☉ (orange)",
              showlegend: true,
            }}
            height={560}
          />
          <div className="mt-2 text-[11px] leading-relaxed text-slate-500">
            <ExplainText
              text={
                "Every curve is a published EEP-matched track (no smoothing). Gray dots mark the " +
                "ZAMS proxy (max surface gravity), ✕ marks the MS-end proxy (first point with " +
                "L > 1.3 × L_ZAMS), yellow stars are literature reference points. Metallicity is " +
                "selected in the controls above; values between the two bundled grids (Z = 0.001, " +
                "Z = 0.014) are interpolated in log Z."
              }
            />
          </div>
          {isoAges.length > 0 && (
            <div className="mt-1 text-[11px] leading-relaxed text-slate-500">
              <b>Dashed isochrones:</b>{" "}
              <ExplainText
                text={
                  "all stars of one age, ordered by initial mass and labeled at the curve end " +
                  "and in the legend; hovering a point also lists the masses omitted from that " +
                  "curve."
                }
              />{" "}
              {isoFootnotes.length > 0 && <> — {isoFootnotes.join(" · ")}</>}. Omitted masses are
              never extrapolated beyond a track's stored age range.
            </div>
          )}
        </section>
      )}

      {view === "star" && p && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
            {[
              { l: "Luminosity", v: `${p.luminosity_msun.toPrecision(4)} L☉` },
              { l: "Radius", v: `${p.radius_msun.toPrecision(4)} R☉` },
              { l: "Teff", v: `${p.teff_K.toFixed(0)} K` },
              { l: "Spectral class", v: p.spectral_class },
              p.ms_lifetime_Gyr !== undefined
                ? { l: "MS lifetime", v: `${p.ms_lifetime_Gyr.toPrecision(3)} Gyr` }
                : { l: "MS lifetime (proxy)", v: `${(p.ms_lifetime_Gyr_proxy ?? 0).toPrecision(3)} Gyr` },
              p.expected_remnant
                ? { l: "Remnant", v: p.expected_remnant }
                : { l: "Evaluated age", v: `${((p.age_yr ?? 0) / 1e9).toPrecision(3)} Gyr` },
            ].map((s) => (
              <div key={s.l} className="card">
                <div className="text-[10px] uppercase tracking-wide text-slate-500">{s.l}</div>
                <div className="mt-1 text-sm font-semibold text-cyan-200">{s.v}</div>
              </div>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="card">
              <h2 className="mb-2 font-semibold text-slate-200">Hertzsprung–Russell diagram</h2>
              <Plot
                data={hrData}
                layout={{
                  xaxis: { title: "Teff [K]", type: "log", autorange: "reversed", gridcolor: c.grid },
                  yaxis: { title: "L [L☉]", type: "log", gridcolor: c.grid },
                  title: `${p.model_fidelity}`,
                }}
                height={420}
              />
            </section>
            <section className="card">
              <h2 className="mb-2 font-semibold text-slate-200">Published reference stars</h2>
              <table className="w-full text-left text-xs">
                <thead className="text-slate-500">
                  <tr>
                    <th className="pb-1">Star</th>
                    <th>M [M☉]</th>
                    <th>Teff [K]</th>
                    <th>L [L☉]</th>
                    <th>Model ΔTeff</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300">
                  {refs.map((r) => (
                    <tr key={r.name} className="border-t border-slate-800">
                      <td className="py-1.5">{r.name}</td>
                      <td>{r.mass_msun}</td>
                      <td>{r.teff_K}</td>
                      <td>{r.lum_msun}</td>
                      <td className="text-slate-500">{r.source.slice(0, 40)}…</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mt-3 text-[11px] leading-relaxed text-slate-500">
                <b>Model assumptions:</b>
                <ul className="mt-1 list-inside list-disc space-y-0.5">
                  {p.assumptions.map((a) => (
                    <li key={a}>
                      <ExplainText text={a} />
                    </li>
                  ))}
                </ul>
                <div className="mt-2">
                  <b>Sources:</b> <ExplainText text={p.references.join("; ")} />
                </div>
              </div>
            </section>
          </div>
        </>
      )}

      {view === "star" && !p && (
        <section className="card text-sm text-slate-500">
          Compute a stellar model to see HR placement, lifetime, classification and comparisons
          against published values (Sun, Sirius A, Vega, Proxima…).
        </section>
      )}

      {prov && (
        <section className="card">
          <h2 className="mb-2 font-semibold text-slate-200">Data provenance</h2>
          <div className="grid gap-4 text-[11px] leading-relaxed text-slate-300 md:grid-cols-2">
            <div>
              <div className="eyebrow mb-1">Dataset</div>
              <div>{prov.dataset}</div>
              <div className="mt-1 text-slate-400">
                Z = {evalZ}
                {prov.metallicities_z && (
                  <> · grids at Z = {prov.metallicities_z.join(" and ")} (interpolated in log Z)</>
                )}
                {prov.grid && (
                  <> · {prov.grid.n_tracks} tracks, {prov.grid.mass_range_msun[0]}–{prov.grid.mass_range_msun[1]} M☉</>
                )}
              </div>
              {prov.grids && (
                <div className="mt-1 text-slate-400">
                  {Object.entries(prov.grids).map(([z, g]) => (
                    <div key={z}>Z = {z}: Y = {g.helium_y}, {g.n_rows} rows ({g.provenance_file})</div>
                  ))}
                </div>
              )}
              {prov.grid && (
                <div className="mt-1 text-slate-400">Interpolation: {prov.grid.interpolation}</div>
              )}
              <div className="mt-1">
                <a className="border-b border-slate-100 hover:opacity-60" href={prov.source_page} target="_blank" rel="noreferrer">
                  {prov.source_page}
                </a>
              </div>
            </div>
            <div>
              <div className="eyebrow mb-1">Required citations</div>
              <ul className="list-inside list-disc space-y-0.5">
                {prov.citations.map((c) => <li key={c}>{c}</li>)}
              </ul>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}