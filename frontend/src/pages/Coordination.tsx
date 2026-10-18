import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
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

interface CoordNode {
  id: string;
  agent: string;
  label: string;
  status: string;
  depends_on: string[];
}
interface RunRow {
  id: string;
  agent: string;
  node: string;
  status: string;
  evidence: Array<{ tool: string; result_summary?: string }>;
  error: string;
}
interface CoordData {
  session: { id: string; domain?: string; objective?: string };
  nodes: CoordNode[];
  edges: Array<{ source: string; target: string }>;
  runs: RunRow[];
}
interface SessionRow {
  id: string;
  title: string;
}

const STATUS_COLOR: Record<string, string> = {
  succeeded: "#10b981",
  failed: "#f43f5e",
  running: "#f59e0b",
  blocked: "#a855f7",
  pending: "#475569",
};

function AgentNode({ data }: { data: { label: string; agent: string; status: string } }) {
  const color = STATUS_COLOR[data.status] ?? "#475569";
  return (
    <div
      className="rounded-xl border-2 bg-slate-900 px-4 py-3 shadow-lg"
      style={{ borderColor: color, minWidth: 170 }}
    >
      <Handle type="target" position={Position.Top} className="!bg-slate-500" />
      <div className="text-sm font-semibold text-slate-100">{data.label}</div>
      <div className="text-xs text-slate-400">{data.agent}</div>
      <div className="mt-1 text-[10px] font-medium uppercase tracking-wider" style={{ color }}>
        {data.status}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-slate-500" />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

export default function Coordination() {
  const { sessionId: routeId } = useParams();
  const [selected, setSelected] = useState<string>(routeId ?? "");

  const sessions = useQuery({
    queryKey: ["all-sessions"],
    queryFn: async () => {
      const projects = await api<Array<{ id: string; title: string }>>("/api/projects");
      const lists = await Promise.all(
        projects.map((p) =>
          api<{ sessions: SessionRow[] }>(`/api/projects/${p.id}`).then((d) => d.sessions ?? []),
        ),
      );
      return lists.flat();
    },
  });

  const sessionId = selected || routeId || sessions.data?.[0]?.id || "";

  const coord = useQuery({
    queryKey: ["coord", sessionId],
    queryFn: () => api<CoordData>(`/api/agents/runs/${sessionId}`),
    enabled: Boolean(sessionId),
    refetchInterval: 4000,
  });

  const { nodes, edges } = useMemo(() => {
    const data = coord.data;
    if (!data) return { nodes: [] as Node[], edges: [] as Edge[] };
    const cols = Math.max(1, data.nodes.length);
    const flowNodes: Node[] = data.nodes.map((n, i) => ({
      id: n.id,
      type: "agent",
      position: { x: (i % 4) * 240, y: Math.floor(i / 4) * 150 },
      data: { label: n.label, agent: n.agent, status: n.status },
    }));
    const flowEdges: Edge[] = data.edges.map((e) => ({
      id: `${e.source}->${e.target}`,
      source: e.source,
      target: e.target,
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: "#475569" },
    }));
    void cols;
    return { nodes: flowNodes, edges: flowEdges };
  }, [coord.data]);

  const selectedRun = coord.data?.runs.find((r) => r.id === selected) ?? null;
  const runsForNode = coord.data?.runs.filter((r) => r.node === selected);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Agent Coordination Center</h1>
          <p className="text-sm text-slate-400">
            Live dependency graph of the investigation: handoffs, status, and evidence.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select className="input w-72" value={sessionId} onChange={(e) => setSelected(e.target.value)}>
            {(sessions.data ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.title} ({s.id.slice(0, 8)})
              </option>
            ))}
          </select>
          <Link to={`/workspace/${sessionId}`} className="btn-ghost">
            Workspace →
          </Link>
        </div>
      </header>

      {!sessionId && <div className="card text-sm text-slate-500">No sessions found.</div>}

      {sessionId && (
        <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
          <div className="card h-[540px] p-0">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              fitView
              nodesDraggable
              proOptions={{ hideAttribution: true }}
              onNodeClick={(_, node) => setSelected(node.id)}
            >
              <MiniMap pannable zoomable nodeColor={(n) => STATUS_COLOR[n.data.status as string] ?? "#475569"} />
              <Controls />
              <Background gap={24} color="#1e293b" />
            </ReactFlow>
          </div>

          <div className="space-y-4">
            <section className="card">
              <h2 className="mb-2 font-semibold text-slate-200">Node evidence</h2>
              {runsForNode && runsForNode.length > 0 ? (
                <div className="space-y-3">
                  {runsForNode.map((r) => (
                    <div key={r.id} className="rounded-lg border border-slate-800 p-2">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-violet-300">{r.agent}</span>
                        <span
                          className={`badge ${
                            r.status === "succeeded"
                              ? "bg-emerald-500/15 text-emerald-300"
                              : "bg-rose-500/15 text-rose-300"
                          }`}
                        >
                          {r.status}
                        </span>
                      </div>
                      {r.error && <div className="text-xs text-rose-400">{r.error}</div>}
                      <ul className="mt-1 space-y-1">
                        {r.evidence.map((e, i) => (
                          <li key={i} className="text-xs text-slate-400">
                            <span className="mono text-cyan-400">{e.tool}</span>
                            {e.result_summary ? ` — ${e.result_summary}` : ""}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500">
                  {selectedRun ? "" : "Click a node to inspect the evidence it produced."}
                </p>
              )}
            </section>

            <section className="card text-xs text-slate-400">
              <h2 className="mb-2 text-sm font-semibold text-slate-200">Legend</h2>
              <div className="grid grid-cols-2 gap-1">
                {Object.entries(STATUS_COLOR).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2">
                    <span className="h-3 w-3 rounded" style={{ background: v }} />
                    {k}
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}