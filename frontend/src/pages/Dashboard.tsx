import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";

interface Project {
  id: string;
  title: string;
  objective: string;
  domain: string;
  status: string;
  created_at: string;
}

interface Experiment {
  id: string;
  name: string;
  status: string;
  sweep_type?: string;
  summary: Record<string, number>;
  created_at: string;
}

interface Episodic {
  id: string;
  objective: string;
  status: string;
  created_at: string;
}

function Stat({ label, value, tone = "cyan" }: { label: string; value: string; tone?: string }) {
  const colors: Record<string, string> = {
    cyan: "text-cyan-300",
    green: "text-emerald-300",
    amber: "text-amber-300",
    violet: "text-violet-300",
  };
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${colors[tone]}`}>{value}</div>
    </div>
  );
}

export default function Dashboard() {
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => api<Project[]>("/api/projects") });
  const experiments = useQuery({
    queryKey: ["experiments"],
    queryFn: () => api<Experiment[]>("/api/experiments"),
  });
  const episodes = useQuery({
    queryKey: ["episodes"],
    queryFn: () => api<Episodic[]>("/api/memory/episodic"),
  });
  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: () => api<{ count: number }>("/api/agents"),
  });

  const completed = (experiments.data ?? []).filter((e) => e.status === "completed");
  const stableFraction =
    completed.length > 0
      ? (
          completed.reduce((acc, e) => acc + (e.summary?.stability_fraction ?? 0), 0) /
          completed.length
        ).toFixed(2)
      : "—";

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-100">Research Dashboard</h1>
        <p className="text-sm text-slate-400">
          Active investigations, recent experiments, and durable research memory.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Projects" value={String(projects.data?.length ?? "…")} />
        <Stat label="Experiments executed" value={String(experiments.data?.length ?? "…")} tone="violet" />
        <Stat label="Episodes in memory" value={String(episodes.data?.length ?? "…")} tone="green" />
        <Stat label="Mean sweep stability" value={String(stableFraction)} tone="amber" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-semibold text-slate-200">Research projects</h2>
            <Link to="/research/workspace" className="btn-primary text-xs">
              New investigation
            </Link>
          </div>
          <div className="space-y-2">
            {(projects.data ?? []).length === 0 && (
              <p className="text-sm text-slate-500">
                No projects yet — open the Research Workspace to start one.
              </p>
            )}
            {(projects.data ?? []).map((p) => (
              <Link
                key={p.id}
                to="/research/workspace"
                className="block rounded-lg border border-slate-800 bg-slate-950/50 p-3 hover:border-cyan-700"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-200">{p.title}</span>
                  <span className="badge bg-cyan-500/15 text-cyan-300">{p.domain}</span>
                </div>
                <div className="mt-1 line-clamp-1 text-xs text-slate-500">{p.objective}</div>
              </Link>
            ))}
          </div>
        </section>

        <section className="card">
          <h2 className="mb-3 font-semibold text-slate-200">Recent experiments</h2>
          <div className="space-y-2">
            {(experiments.data ?? []).slice(0, 6).map((e) => (
              <div
                key={e.id}
                className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/50 p-3"
              >
                <div>
                  <div className="text-sm text-slate-200">{e.name}</div>
                  <div className="text-xs text-slate-500">
                    {new Date(e.created_at).toLocaleString()}
                  </div>
                </div>
                <span
                  className={`badge ${
                    e.status === "completed"
                      ? "bg-emerald-500/15 text-emerald-300"
                      : e.status === "failed"
                        ? "bg-rose-500/15 text-rose-300"
                        : "bg-amber-500/15 text-amber-300"
                  }`}
                >
                  {e.status}
                </span>
              </div>
            ))}
            {(experiments.data ?? []).length === 0 && (
              <p className="text-sm text-slate-500">No experiments executed yet.</p>
            )}
          </div>
        </section>
      </div>

      <section className="card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-slate-200">Recent episodes (durable memory)</h2>
          <Link to="/research/memory" className="btn-ghost text-xs">
            Open Memory Explorer
          </Link>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {(episodes.data ?? []).slice(0, 6).map((ep) => (
            <div key={ep.id} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
              <div className="line-clamp-2 text-sm text-slate-300">{ep.objective}</div>
              <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                <span
                  className={`badge ${
                    ep.status.startsWith("completed")
                      ? "bg-emerald-500/15 text-emerald-300"
                      : "bg-amber-500/15 text-amber-300"
                  }`}
                >
                  {ep.status}
                </span>
                <span>{new Date(ep.created_at).toLocaleDateString()}</span>
                <span className="mono">{ep.id.slice(0, 8)}</span>
              </div>
            </div>
          ))}
          {(episodes.data ?? []).length === 0 && (
            <p className="text-sm text-slate-500">
              Completed investigations will persist here across sessions.
            </p>
          )}
        </div>
      </section>

      <footer className="text-xs text-slate-600">
        {agents.data ? `${agents.data.count} registered agents` : "loading agents…"} · every
        figure shown originates from executed tool runs
      </footer>
    </div>
  );
}