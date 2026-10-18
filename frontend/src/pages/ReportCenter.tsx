import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, downloadArtifact, getToken } from "../api";

interface SessionRow {
  id: string;
  title: string;
}
interface ArtifactRow {
  id: string;
  kind: string;
  filename: string;
  sha256: string;
  size_bytes: number;
  meta: Record<string, unknown>;
  created_at: string;
}

export default function ReportCenter() {
  const [sessionId, setSessionId] = useState("");
  const [text, setText] = useState("");

  const sessions = useQuery({
    queryKey: ["all-sessions"],
    queryFn: async () => {
      const projects = await api<Array<{ id: string }>>("/api/projects");
      const lists = await Promise.all(
        projects.map((p) =>
          api<{ sessions: SessionRow[] }>(`/api/projects/${p.id}`).then((d) => d.sessions ?? []),
        ),
      );
      return lists.flat();
    },
  });

  useEffect(() => {
    if (!sessionId && sessions.data?.length) setSessionId(sessions.data[0].id);
  }, [sessions.data, sessionId]);

  const artifacts = useQuery({
    queryKey: ["artifacts", sessionId],
    queryFn: () => api<ArtifactRow[]>(`/api/sessions/${sessionId}/artifacts`),
    enabled: Boolean(sessionId),
  });

  const reports = (artifacts.data ?? []).filter((a) => a.kind === "report");

  useEffect(() => {
    if (!reports.length) return;
    let cancelled = false;
    void fetch(`/api/artifacts/${reports[0].id}/download`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    })
      .then((r) => (r.ok ? r.text() : ""))
      .then((t) => !cancelled && setText(t))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [reports]);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Scientific Report Center</h1>
          <p className="text-sm text-slate-400">
            Reproducible reports: methodology, equations, executed-check results, artifacts and
            limitations — generated only from persisted evidence.
          </p>
        </div>
        <select className="input w-72" value={sessionId} onChange={(e) => setSessionId(e.target.value)}>
          {(sessions.data ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.title} ({s.id.slice(0, 8)})
            </option>
          ))}
        </select>
      </header>

      <section className="card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-slate-200">Reports</h2>
          <Link to={`/workspace/${sessionId}`} className="btn-ghost text-xs">
            ← Back to workspace
          </Link>
        </div>
        {reports.length === 0 && (
          <p className="text-sm text-slate-500">
            No report for this session yet — run an investigation; the Report Generation Agent
            produces one at the end of the graph.
          </p>
        )}
        <div className="space-y-2">
          {reports.map((r) => (
            <div key={r.id} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/50 p-3">
              <div>
                <div className="text-sm text-slate-200">{r.filename}</div>
                <div className="mono text-[10px] text-slate-600">
                  sha256 {r.sha256} · {r.size_bytes} B · {new Date(r.created_at).toLocaleString()}
                </div>
                {typeof r.meta.n_validations === "number" && (
                  <div className="text-[10px] text-slate-500">
                    validations: {String(r.meta.n_passed)}/{String(r.meta.n_validations)} passed ·
                    artifacts linked: {String(r.meta.n_artifacts ?? 0)}
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                <button className="btn-ghost text-xs" onClick={() => downloadArtifact(r.id, r.filename)}>
                  ⬇ Download
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {text && (
        <section className="card">
          <h2 className="mb-2 font-semibold text-slate-200">Preview (markdown)</h2>
          <pre className="mono max-h-[600px] overflow-auto whitespace-pre-wrap rounded bg-slate-950/70 p-4 text-[12px] leading-relaxed text-slate-300">
            {text}
          </pre>
        </section>
      )}
    </div>
  );
}