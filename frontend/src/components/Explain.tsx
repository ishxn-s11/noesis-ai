/**
 * Inline explainer: highlights every glossary term inside arbitrary text
 * (findings, agent messages, paper claims) and opens a shared dialog with the
 * plain-language explanation, formula and references on click.

 * Matching mirrors backend `app.core.glossary.find_terms` exactly (longest-
 * first claiming, word boundaries, single trailing plural 's'), so the API's
 * POST /api/explain and the UI highlight the same spans.
 */
import { useEffect, useState, useSyncExternalStore } from "react";
import { api } from "../api";

export interface GlossaryTerm {
  id: string;
  term: string;
  aka: string[];
  category: string;
  short: string;
  explain: string;
  formula: string;
  units: string[];
  where_used: string[];
  see_also: string[];
  references: string[];
}
interface GlossaryPayload {
  terms: GlossaryTerm[];
  categories: string[];
  n_terms: number;
  note: string;
}

/* -------------------------------------------------- glossary (cached once) */
let glossaryPromise: Promise<GlossaryTerm[]> | null = null;

export function loadGlossary(): Promise<GlossaryTerm[]> {
  if (!glossaryPromise) {
    glossaryPromise = api<GlossaryPayload>("/api/glossary")
      .then((p) => p.terms)
      .catch(() => []); // explainer degrades to plain text if unavailable
  }
  return glossaryPromise;
}

export function useGlossary(): GlossaryTerm[] {
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  useEffect(() => {
    let alive = true;
    void loadGlossary().then((t) => {
      if (alive) setTerms(t);
    });
    return () => {
      alive = false;
    };
  }, []);
  return terms;
}

/* --------------------------------------------------- shared dialog store */
let selected: GlossaryTerm | null = null;
const listeners = new Set<() => void>();

export function openExplain(term: GlossaryTerm): void {
  selected = term;
  listeners.forEach((l) => l());
}
export function closeExplain(): void {
  selected = null;
  listeners.forEach((l) => l());
}
function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useSelectedTerm(): GlossaryTerm | null {
  return useSyncExternalStore(subscribe, () => selected, () => selected);
}

/* ------------------------------------------------------------ term matching */
const WORD = /[\p{L}\p{N}]/u;

function matchKeys(t: GlossaryTerm): string[] {
  const head = t.term.split("(")[0].trim();
  const out: string[] = [];
  for (const s of [t.term, head, ...(t.aka ?? [])]) {
    const v = s.trim();
    if (v.length >= 2 && !out.includes(v)) out.push(v);
  }
  return out;
}

interface Hit {
  start: number;
  end: number;
  term: GlossaryTerm;
}

export function findMatches(text: string, terms: GlossaryTerm[]): Hit[] {
  if (!text || terms.length === 0) return [];
  const low = text.toLowerCase();
  const candidates: Array<[string, GlossaryTerm]> = [];
  for (const t of terms) for (const k of matchKeys(t)) candidates.push([k.toLowerCase(), t]);
  candidates.sort((a, b) => b[0].length - a[0].length);

  const claimed: Array<[number, number]> = [];
  const hits: Hit[] = [];
  for (const [key, term] of candidates) {
    let from = 0;
    for (;;) {
      const i = low.indexOf(key, from);
      from = i + 1;
      if (i < 0) break;
      let j = i + key.length;
      if (low[j] === "s" && (j + 1 >= low.length || !WORD.test(low[j + 1]))) j += 1;
      if (i > 0 && WORD.test(low[i - 1])) continue;
      if (j < low.length && WORD.test(low[j])) continue;
      if (claimed.some(([a, b]) => i < b && a < j)) continue;
      claimed.push([i, j]);
      hits.push({ start: i, end: j, term });
    }
  }
  hits.sort((a, b) => a.start - b.start);
  return hits;
}

/* -------------------------------------------------------------- ExplainText */
export function ExplainText({ text, className }: { text: string; className?: string }) {
  const terms = useGlossary();
  if (!text) return null;
  const hits = findMatches(text, terms);
  if (hits.length === 0) return <span className={className}>{text}</span>;

  const parts: React.ReactNode[] = [];
  let cursor = 0;
  hits.forEach((h, i) => {
    if (h.start > cursor) parts.push(<span key={`p${i}`}>{text.slice(cursor, h.start)}</span>);
    parts.push(
      <button
        key={`t${i}`}
        type="button"
        className="cursor-help underline decoration-dotted underline-offset-4 hover:decoration-solid"
        style={{ textDecorationColor: "rgb(var(--cy-500) / 0.7)" }}
        onClick={() => openExplain(h.term)}
        title={`Explain: ${h.term.term}`}
      >
        {text.slice(h.start, h.end)}
      </button>,
    );
    cursor = h.end;
  });
  if (cursor < text.length) parts.push(<span key="tail">{text.slice(cursor)}</span>);
  return <span className={className}>{parts}</span>;
}

/* -------------------------------------------------------------- the dialog */
export function ExplainDialog() {
  const term = useSelectedTerm();
  const glossary = useGlossary();

  useEffect(() => {
    if (!term) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeExplain();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [term]);

  if (!term) return null;
  const seeAlso = (term.see_also ?? [])
    .map((id) => glossary.find((g) => g.id === id))
    .filter((g): g is GlossaryTerm => Boolean(g));

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      onClick={closeExplain}
    >
      <div
        className="card max-h-[85vh] w-full max-w-xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="eyebrow">{term.category}</div>
            <h3 className="display-sm mt-1">{term.term}</h3>
            {term.aka?.length > 0 && (
              <div className="mt-1 text-xs text-slate-500">also: {term.aka.join(" · ")}</div>
            )}
          </div>
          <button className="btn-ghost text-xs" onClick={closeExplain}>
            Close
          </button>
        </div>

        <p className="mt-4 text-sm font-semibold text-cyan-300">{term.short}</p>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
          {term.explain}
        </p>

        {term.formula && (
          <div className="mt-3 rounded-none border border-slate-700 bg-slate-950/60 p-3">
            <div className="eyebrow mb-1">Formula / relation</div>
            <div className="mono text-sm text-cyan-200">{term.formula}</div>
            {term.units?.length > 0 && (
              <div className="mt-1 text-xs text-slate-500">units: {term.units.join(", ")}</div>
            )}
          </div>
        )}

        {term.where_used?.length > 0 && (
          <div className="mt-3 text-xs text-slate-400">
            <span className="eyebrow">Where used: </span>
            {term.where_used.join(" · ")}
          </div>
        )}

        {seeAlso.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span className="eyebrow">See also</span>
            {seeAlso.map((t) => (
              <button key={t.id} className="btn-ghost text-xs" onClick={() => openExplain(t)}>
                {t.term}
              </button>
            ))}
          </div>
        )}

        <div className="mt-4 border-t border-slate-800 pt-3 text-[11px] leading-relaxed text-slate-500">
          {term.references?.map((r) => (
            <div key={r}>— {r}</div>
          ))}
        </div>
      </div>
    </div>
  );
}
