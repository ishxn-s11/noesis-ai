import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

type Tab = "episodic" | "semantic" | "procedural";

interface Row {
  id: string;
  [key: string]: unknown;
}

const TABS: Array<{ id: Tab; label: string; blurb: string }> = [
  { id: "episodic", label: "Episodic", blurb: "Experiment records with full provenance" },
  { id: "semantic", label: "Semantic", blurb: "Evidence-backed knowledge & hypotheses" },
  { id: "procedural", label: "Procedural", blurb: "Reusable workflows (approval-gated)" },
];

export default function MemoryExplorer() {
  const [tab, setTab] = useState<Tab>("episodic");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Row | null>(null);

  const path = `/api/memory/${tab}${query ? `?q=${encodeURIComponent(query)}` : ""}`;
  const results = useQuery({
    queryKey: ["memory", tab, query],
    queryFn: () => api<Row[]>(path),
  });

  const statusTone = (s: unknown) =>
    s === "verified" || s === "approved" || s === "established"
      ? "bg-emerald-500/15 text-emerald-300"
      : s === "hypothesis" || s === "pending"
        ? "bg-amber-500/15 text-amber-300"
        : s === "rejected"
          ? "bg-rose-500/15 text-rose-300"
          : "bg-slate-700/50 text-slate-300";

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold text-slate-100">Scientific Memory Explorer</h1>
        <p className="text-sm text-slate-400">
          Search episodic, semantic and procedural memory — with versions, provenance and
          validation status.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? "btn-primary" : "btn-ghost"}
            onClick={() => {
              setTab(t.id);
              setSelected(null);
            }}
          >
            {t.label}
          </button>
        ))}
        <form
          className="ml-auto flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(q.trim());
          }}
        >
          <input
            className="input w-72"
            placeholder={`semantic search over ${tab}…`}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <button className="btn-primary">Search</button>
        </form>
      </div>
      <div className="text-xs text-slate-500">
        {TABS.find((t) => t.id === tab)?.blurb} ·{" "}
        {(results.data ?? []).length} record{(results.data ?? []).length === 1 ? "" : "s"}
        {query && <> for “{query}”</>}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="space-y-2">
          {(results.data ?? []).map((row) => {
            const title = (row.title ?? row.objective ?? row.name) as string;
            const status = (row.status ?? row.validation_status) as string | undefined;
            const version = row.version as number | undefined;
            return (
              <button
                key={row.id}
                onClick={() => setSelected(row)}
                className={`block w-full rounded-xl border p-3 text-left transition ${
                  selected?.id === row.id
                    ? "border-cyan-700 bg-cyan-500/10"
                    : "border-slate-800 bg-slate-900/60 hover:border-slate-600"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-slate-200">{title}</span>
                  <span className="flex items-center gap-1">
                    {status && <span className={`badge ${statusTone(status)}`}>{status}</span>}
                    {version && version > 1 && (
                      <span className="badge bg-slate-800 text-slate-400">v{version}</span>
                    )}
                  </span>
                </div>
                <div className="mt-1 line-clamp-2 text-xs text-slate-500">
                  {(row.content ?? row.description ?? row.objective ?? "") as string}
                </div>
                {tab === "semantic" && Array.isArray(row.source_refs) && row.source_refs.length > 0 && (
                  <div className="mt-1 truncate text-[10px] text-cyan-600">
                    refs: {(row.source_refs as string[]).join(" · ")}
                  </div>
                )}
              </button>
            );
          })}
          {(results.data ?? []).length === 0 && (
            <div className="card text-sm text-slate-500">Nothing stored yet for this view.</div>
          )}
        </section>

        <section className="card lg:sticky lg:top-6 lg:max-h-[70vh] lg:overflow-auto">
          <h2 className="mb-2 font-semibold text-slate-200">Record detail</h2>
          {!selected && <p className="text-sm text-slate-500">Select a record.</p>}
          {selected && (
            <pre className="mono whitespace-pre-wrap rounded bg-slate-950/70 p-3 text-[11px] leading-relaxed text-slate-300">
              {JSON.stringify(selected, null, 2)}
            </pre>
          )}
        </section>
      </div>
    </div>
  );
}