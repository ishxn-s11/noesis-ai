import { useMemo, useState } from "react";
import { ExplainText, findMatches, useGlossary, type GlossaryTerm } from "../components/Explain";

const CATEGORY_BLURB: Record<string, string> = {
  stellar: "Stars, evolution tracks, HR diagram, lifetimes",
  cosmology: "Expansion, distances, ΛCDM, posteriors",
  celestial: "Orbits, N-body integration, conservation",
  observation: "Archives, catalogs, photometry, FITS",
  statistics: "Bayesian inference and uncertainty",
  methods: "Platform-wide scientific practice",
};

/** Free-text demo: paste any finding and every known term highlights live. */
function LiveDemo({ glossary }: { glossary: GlossaryTerm[] }) {
  const [text, setText] = useState(
    "The HR diagram places each isochrone by effective temperature and luminosity. " +
      "A Hubble constant of 73.0 km/s/Mpc implies a younger universe than Planck's 67.4; " +
      "the posterior's credible interval does not overlap, which is the Hubble tension. " +
      "Orbital stability was checked via energy drift under IAS15 integration.",
  );
  const hits = useMemo(() => findMatches(text, glossary), [text, glossary]);
  return (
    <section className="card">
      <h2 className="mb-1 font-semibold text-slate-200">Explain any text</h2>
      <p className="mb-3 text-xs text-slate-500">
        Paste a finding, an abstract, a report passage — every term this platform can explain
        is highlighted. Click a highlight for the plain-language version.
      </p>
      <textarea
        className="input h-28 resize-y"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Paste any scientific text…"
      />
      <div className="mt-3 rounded-none border border-slate-700 bg-slate-950/60 p-3 text-sm leading-relaxed text-slate-300">
        <ExplainText text={text} />
      </div>
      <div className="mt-2 text-xs text-slate-500">
        {hits.length} highlighted occurrence{hits.length === 1 ? "" : "s"} ·{" "}
        {new Set(hits.map((h) => h.term.id)).size} distinct term
        {new Set(hits.map((h) => h.term.id)).size === 1 ? "" : "s"} found
      </div>
    </section>
  );
}

export default function Explainer() {
  const glossary = useGlossary();
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");

  const categories = useMemo(() => {
    const used = new Set(glossary.map((t) => t.category));
    return [...used];
  }, [glossary]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return glossary.filter((t) => {
      if (cat && t.category !== cat) return false;
      if (!needle) return true;
      return (
        t.term.toLowerCase().includes(needle) ||
        t.short.toLowerCase().includes(needle) ||
        t.explain.toLowerCase().includes(needle) ||
        (t.aka ?? []).some((a) => a.toLowerCase().includes(needle))
      );
    });
  }, [glossary, q, cat]);

  return (
    <div className="space-y-5">
      <header>
        <div className="eyebrow">Reference</div>
        <h1 className="display mt-2">Explainer</h1>
        <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-slate-300">
          Every complex term and finding on this platform links back to this curated glossary:
          plain-language definitions, the formula behind each relation, where it is used, and the
          scientific source. Nothing here is generated — each entry cites its reference.
        </p>
      </header>

      <section className="card flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-400">
          Search terms
          <input
            className="input mt-1 w-72"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. isochrone, posterior, parallax…"
          />
        </label>
        <label className="text-xs text-slate-400">
          Category
          <select className="input mt-1 w-48" value={cat} onChange={(e) => setCat(e.target.value)}>
            <option value="">— all —</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <span className="text-xs text-slate-500">
          {filtered.length} of {glossary.length} terms
        </span>
      </section>

      <LiveDemo glossary={glossary} />

      <div className="grid gap-4 lg:grid-cols-2">
        {filtered.map((t) => (
          <section key={t.id} className="card">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="font-semibold text-slate-200">{t.term}</h2>
              <span className="badge bg-cyan-500/10 text-cyan-300">{t.category}</span>
            </div>
            {t.aka?.length > 0 && (
              <div className="mt-0.5 text-[11px] text-slate-500">also: {t.aka.join(" · ")}</div>
            )}
            <p className="mt-2 text-sm font-semibold text-cyan-300">{t.short}</p>
            <p className="mt-2 text-sm leading-relaxed text-slate-300">{t.explain}</p>
            {t.formula && (
              <div className="mono mt-2 text-xs text-cyan-200">{t.formula}</div>
            )}
            <div className="mt-3 border-t border-slate-800 pt-2 text-[11px] text-slate-500">
              <div>
                <span className="eyebrow">Used in: </span>
                {t.where_used.join(" · ")}
              </div>
              {t.references?.map((r) => (
                <div key={r}>— {r}</div>
              ))}
            </div>
          </section>
        ))}
        {filtered.length === 0 && (
          <section className="card text-sm text-slate-500">
            No term matches “{q}”. The glossary covers terms shown across the labs and agent
            findings — try a shorter query.
          </section>
        )}
      </div>

      <p className="text-[11px] text-slate-500">
        {categories.map((c) => `${c}: ${CATEGORY_BLURB[c] ?? ""}`).join(" · ")}
      </p>
    </div>
  );
}
