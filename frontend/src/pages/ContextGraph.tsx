import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "../api";

interface CtxNode {
  label: string;
  id: string;
  title: string;
  status: string;
  created_at: string;
  via?: string; // "neighbor" = reached by one-hop expansion
}
interface CtxEdge {
  source: string;
  type: string;
  target: string;
  target_label: string;
  target_title: string;
}
interface CtxGraph {
  available: boolean;
  reason?: string;
  nodes: CtxNode[];
  edges: CtxEdge[];
  graph?: { enabled: boolean; available: boolean; reason?: string };
}

const LABEL_ORDER = [
  "Question", "Session", "Episode", "Procedure",
  "Experiment", "Validation", "Knowledge", "Artifact",
];
const LABEL_COLOR: Record<string, string> = {
  Question: "#38bdf8", Session: "#a78bfa", Episode: "#10b981",
  Procedure: "#f59e0b", Experiment: "#f43f5e", Validation: "#22d3ee",
  Knowledge: "#e879f9", Artifact: "#94a3b8",
};

function CtxCard({ data }: {
  data: { label: string; title: string; status: string; neighbor: boolean };
}) {
  const color = LABEL_COLOR[data.label] ?? "#475569";
  return (
    <div
      className="rounded-lg border-2 bg-slate-900 px-3 py-2 shadow-lg"
      style={{
        borderColor: color,
        minWidth: 180,
        maxWidth: 220,
        opacity: data.neighbor ? 0.75 : 1,
        borderStyle: data.neighbor ? "dashed" : "solid",
      }}
    >
      <Handle type="target" position={Position.Left} className="!bg-slate-500" />
      <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color }}>
        {data.label}{data.neighbor ? " · 1-hop" : ""}
      </div>
      <div className="mt-0.5 line-clamp-2 text-xs text-slate-200" title={data.title}>
        {data.title || data.label}
      </div>
      {data.status && (
        <div className="mt-1 text-[10px] text-slate-500">status: {data.status}</div>
      )}
      <Handle type="source" position={Position.Right} className="!bg-slate-500" />
    </div>
  );
}

const nodeTypes = { ctx: CtxCard };

export default function ContextGraphPage() {
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["context-graph", submitted],
    queryFn: () =>
      api<CtxGraph>(
        `/api/memory/context?limit=40${submitted ? `&q=${encodeURIComponent(submitted)}` : ""}`,
      ),
  });

  const { flowNodes, flowEdges } = useMemo(() => {
    const rows: Record<string, CtxNode[]> = {};
    for (const n of data?.nodes ?? []) (rows[n.label] ??= []).push(n);
    const columns = [
      ...LABEL_ORDER.filter((l) => rows[l]),
      ...Object.keys(rows).filter((l) => !LABEL_ORDER.includes(l)),
    ];
    const pos: Record<string, { x: number; y: number }> = {};
    const fn: Node[] = [];
    columns.forEach((label, col) => {
      (rows[label] ?? []).forEach((n, row) => {
        pos[n.id] = { x: col * 300, y: row * 130 };
        fn.push({
          id: n.id,
          type: "ctx",
          position: pos[n.id],
          data: {
            label: n.label,
            title: n.title,
            status: n.status,
            neighbor: n.via === "neighbor",
          },
        });
      });
    });
    const fe: Edge[] = (data?.edges ?? [])
      .filter((e) => pos[e.source] && pos[e.target])
      .map((e, i) => ({
        id: `e${i}-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        label: e.type,
        labelStyle: { fill: "#94a3b8", fontSize: 10 },
        labelBgStyle: { fill: "#020617", fillOpacity: 0.8 },
        animated: true,
        style: { stroke: "#475569" },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#475569" },
      }));
    return { flowNodes: fn, flowEdges: fe };
  }, [data]);

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col">
      <header className="mb-3 flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-lg font-bold text-slate-100">Context Graph</h1>
          <p className="text-xs text-slate-500">
            FalkorDB research context: questions, sessions, episodes, procedures,
            experiments, validations, knowledge and artifacts — with one-hop
            expansion from matches. Tenant-scoped.
          </p>
        </div>
        <form
          className="ml-auto flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setSubmitted(q.trim());
            setTimeout(() => refetch(), 0);
          }}
        >
          <input
            className="input w-56"
            placeholder="filter keywords…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <button type="submit" className="btn-primary text-xs">Filter</button>
        </form>
      </header>

      {data && !data.available && (
        <div className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          Context graph unavailable{data.reason ? `: ${data.reason}` : ""} — nothing
          below means “no prior context”, only that the graph store is not reachable.
        </div>
      )}

      {error && (
        <div className="mb-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          Failed to load context graph: {String(error)}
        </div>
      )}

      <div className="min-h-0 flex-1 rounded-xl border border-slate-800 bg-slate-950">
        {isLoading ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            Loading context graph…
          </div>
        ) : flowNodes.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-sm text-slate-500">
            <div>No context nodes{submitted ? ` matching “${submitted}”` : ""}.</div>
            <div className="text-xs text-slate-600">
              Complete a research run — agents link questions, episodes, procedures
              and validations into the graph automatically.
            </div>
          </div>
        ) : (
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            nodeTypes={nodeTypes}
            fitView
            minZoom={0.2}
            nodesDraggable
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#1e293b" gap={24} />
            <Controls />
            <MiniMap pannable zoomable nodeColor={(n) =>
              LABEL_COLOR[(n.data as { label: string }).label] ?? "#475569"} />
          </ReactFlow>
        )}
      </div>

      <footer className="mt-2 flex flex-wrap items-center gap-3 text-[10px] text-slate-500">
        {Object.entries(LABEL_COLOR).map(([label, color]) => (
          <span key={label} className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ background: color }} />
            {label}
          </span>
        ))}
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm border border-dashed border-slate-500" />
          neighbor (one-hop expansion)
        </span>
        <span className="ml-auto">
          {flowNodes.length} nodes · {flowEdges.length} edges
        </span>
      </footer>
    </div>
  );
}