import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, artifactUrl, getToken, subscribeJobEvents } from "../api";
import Plot from "../components/Plot";
import { ExplainText } from "../components/Explain";

interface Project {
  id: string;
  title: string;
  domain: string;
}
interface Session {
  id: string;
  title: string;
  state_version: number;
  state: Record<string, unknown>;
  messages?: Message[];
  jobs?: JobRow[];
}
interface Message {
  id: string;
  role: string;
  agent: string;
  content: string;
  created_at: string;
}
interface TimelineEntry {
  id: string;
  agent: string;
  node: string;
  status: string;
  evidence: Array<{ tool: string; result_summary?: string; artifact_ids?: string[] }>;
  error: string;
}
interface ArtifactRow {
  id: string;
  kind: string;
  filename: string;
  sha256: string;
  size_bytes: number;
}
interface JobRow {
  id: string;
  kind: string;
  status: string;
  result?: Record<string, unknown>;
}

const DEMO_QUESTION =
  "How does changing the mass and orbital configuration of a third celestial body affect the orbital stability of an initially stable two-body system?";

export default function Workspace() {
  const { sessionId: routeSession } = useParams();
  const qc = useQueryClient();
  const [projectId, setProjectId] = useState<string>("");
  const [sessionId, setSessionId] = useState<string>(routeSession ?? "");
  const [question, setQuestion] = useState(DEMO_QUESTION);
  const [title, setTitle] = useState("Third-body stability");
  const [activeJob, setActiveJob] = useState<string>("");
  const [liveEvents, setLiveEvents] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const projects = useQuery({ queryKey: ["projects"], queryFn: () => api<Project[]>("/api/projects") });
  const sessionList = useSessionListCache(projects.data ?? []);

  const session = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api<Session>(`/api/sessions/${sessionId}`),
    enabled: Boolean(sessionId),
    refetchInterval: activeJob ? 3000 : false,
  });

  const timeline = useQuery({
    queryKey: ["timeline", sessionId],
    queryFn: () => api<TimelineEntry[]>(`/api/sessions/${sessionId}/timeline`),
    enabled: Boolean(sessionId),
    refetchInterval: activeJob ? 3000 : false,
  });

  const artifacts = useQuery({
    queryKey: ["artifacts", sessionId],
    queryFn: () => api<ArtifactRow[]>(`/api/sessions/${sessionId}/artifacts`),
    enabled: Boolean(sessionId),
    refetchInterval: activeJob ? 4000 : false,
  });

  const job = useQuery({
    queryKey: ["job", activeJob],
    queryFn: () => api<JobRow>(`/api/jobs/${activeJob}`),
    enabled: Boolean(activeJob),
    refetchInterval: 1500,
  });

  useEffect(() => {
    if (!activeJob) return;
    const unsub = subscribeJobEvents(activeJob, (evt) => {
      setLiveEvents((prev) => [...prev.slice(-60), evt]);
      if (evt.type === "graph_finished") {
        qc.invalidateQueries({ queryKey: ["session", sessionId] });
        qc.invalidateQueries({ queryKey: ["timeline", sessionId] });
        qc.invalidateQueries({ queryKey: ["artifacts", sessionId] });
        qc.invalidateQueries({ queryKey: ["experiments"] });
        qc.invalidateQueries({ queryKey: ["episodes"] });
      }
    });
    return unsub;
  }, [activeJob, sessionId, qc]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session.data?.messages?.length, liveEvents.length]);

  async function createAndRun() {
    setBusy(true);
    setError("");
    try {
      let pid = projectId;
      if (!pid) {
        const p = await api<Project>("/api/projects", {
          method: "POST",
          body: JSON.stringify({ title, objective: question }),
        });
        pid = p.id;
        setProjectId(pid);
      }
      const s = await api<Session>(`/api/projects/${pid}/sessions`, {
        method: "POST",
        body: JSON.stringify({ title, research_question: question }),
      });
      setSessionId(s.id);
      const started = await api<{ job: JobRow }>(`/api/sessions/${s.id}/run`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setLiveEvents([]);
      setActiveJob(started.job.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function resumeSession(id: string) {
    setSessionId(id);
    setError("");
    try {
      const started = await api<{ job: JobRow; reused: boolean }>(`/api/sessions/${id}/run`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setLiveEvents([]);
      setActiveJob(started.job.id);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const sweepResult = useMemo(() => {
    const r = job.data?.result as
      | { intermediate?: never; nodes?: Record<string, string> }
      | undefined;
    return r ?? null;
  }, [job.data]);

  const runSummary = (job.data?.result ?? {}) as Record<string, unknown>;

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_420px]">
      <div className="space-y-4">
        <header>
          <h1 className="text-2xl font-bold text-slate-100">AI Research Workspace</h1>
          <p className="text-sm text-slate-400">
            State a research objective; agents plan, execute real tools, validate and persist.
          </p>
        </header>

        <section className="card space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="text-xs text-slate-400">
              Investigation title
              <input className="input mt-1" value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label className="text-xs text-slate-400">
              Existing project (optional)
              <select
                className="input mt-1"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
              >
                <option value="">— create new project —</option>
                {(projects.data ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title} ({p.domain})
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="block text-xs text-slate-400">
            Research question
            <textarea
              className="input mt-1 h-24 resize-y"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-primary" onClick={createAndRun} disabled={busy || !question.trim()}>
              {busy ? "Starting…" : "▶ Run investigation"}
            </button>
            {sessionId && (
              <button className="btn-ghost" onClick={() => resumeSession(sessionId)}>
                Resume this session
              </button>
            )}
            <Link to={`/coordination/${sessionId}`} className="btn-ghost">
              Coordination graph →
            </Link>
            {activeJob && (
              <span className="badge bg-cyan-500/15 text-cyan-300 mono">
                job {activeJob.slice(0, 8)} · {job.data?.status ?? "…"}
              </span>
            )}
          </div>
          {error && <div className="text-sm text-rose-400">{error}</div>}
        </section>

        {/* conversation + agent activity */}
        <section className="card">
          <h2 className="mb-3 font-semibold text-slate-200">Investigation log</h2>
          <div className="max-h-[420px] space-y-3 overflow-y-auto pr-2">
            {session.data?.messages?.length === 0 && (
              <p className="text-sm text-slate-500">
                No messages yet — run the investigation to see agent activity.
              </p>
            )}
            {(session.data?.messages ?? []).map((m) => (
              <div
                key={m.id}
                className={`rounded-lg border p-3 text-sm ${
                  m.role === "researcher"
                    ? "border-cyan-800/60 bg-cyan-500/5"
                    : "border-slate-800 bg-slate-950/60"
                }`}
              >
                <div className="mb-1 flex items-center gap-2 text-xs">
                  <span
                    className={`badge ${
                      m.role === "researcher"
                        ? "bg-cyan-500/15 text-cyan-300"
                        : "bg-violet-500/15 text-violet-300"
                    }`}
                  >
                    {m.role === "researcher" ? "researcher" : m.agent || "agent"}
                  </span>
                  <span className="text-slate-600">{new Date(m.created_at).toLocaleTimeString()}</span>
                </div>
                <div className="whitespace-pre-wrap text-slate-300">
                  <ExplainText text={m.content} />
                </div>
              </div>
            ))}
            {liveEvents
              .filter((e) => String(e.type).startsWith("node_"))
              .map((e, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-xs"
                >
                  <span
                    className={`badge ${
                      e.type === "node_succeeded"
                        ? "bg-emerald-500/15 text-emerald-300"
                        : e.type === "node_failed"
                          ? "bg-rose-500/15 text-rose-300"
                          : "bg-amber-500/15 text-amber-300"
                    }`}
                  >
                    {String(e.type).replace("node_", "")}
                  </span>
                  <span className="text-slate-300">{String(e.node)}</span>
                  <span className="text-slate-600">{String(e.agent ?? "")}</span>
                  {e.summary ? <span className="truncate text-slate-500">{String(e.summary)}</span> : null}
                </div>
              ))}
            <div ref={bottomRef} />
          </div>
          {Boolean(runSummary.nodes) && (
            <div className="mt-3 border-t border-slate-800 pt-3 text-xs text-slate-400">
              Run {String(runSummary.status)} —{" "}
              {Object.entries((runSummary.nodes ?? {}) as Record<string, string>)
                .map(([k, v]) => `${k}:${v}`)
                .join("  ")}
            </div>
          )}
          {!runSummary.nodes && sweepResult === null && job.data?.status && (
            <div className="mt-3 border-t border-slate-800 pt-3 text-xs text-slate-500">
              job status: {job.data.status}
            </div>
          )}
        </section>

        {/* agent timeline with evidence */}
        <section className="card">
          <h2 className="mb-3 font-semibold text-slate-200">
            Agent activity timeline <span className="text-xs font-normal text-slate-500">(evidence: tools that actually ran)</span>
          </h2>
          <div className="space-y-2">
            {(timeline.data ?? []).length === 0 && (
              <p className="text-sm text-slate-500">No agent runs yet.</p>
            )}
            {(timeline.data ?? []).map((t) => (
              <div key={t.id} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-medium text-violet-300">{t.agent}</span>
                  <span className="mono text-xs text-slate-500">{t.node}</span>
                  <span
                    className={`badge ${
                      t.status === "succeeded"
                        ? "bg-emerald-500/15 text-emerald-300"
                        : t.status === "failed"
                          ? "bg-rose-500/15 text-rose-300"
                          : "bg-amber-500/15 text-amber-300"
                    }`}
                  >
                    {t.status}
                  </span>
                </div>
                {t.error && <div className="mt-1 text-xs text-rose-400">{t.error}</div>}
                <ul className="mt-2 space-y-1">
                  {t.evidence.map((ev, i) => (
                    <li key={i} className="text-xs text-slate-400">
                      <span className="mono text-cyan-400">{ev.tool}</span>
                      {ev.result_summary ? <> — {ev.result_summary}</> : null}
                      {ev.artifact_ids?.length ? (
                        <span className="text-slate-600"> (artifacts: {ev.artifact_ids.length})</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* right rail: sessions + artifacts */}
      <div className="space-y-4">
        <section className="card">
          <h2 className="mb-2 font-semibold text-slate-200">Sessions</h2>
          <div className="space-y-1">
            {(projects.data ?? []).length === 0 && (
              <p className="text-xs text-slate-500">Create an investigation to see sessions.</p>
            )}
            {projects.data &&
              sessionList.map((s) => (
                <button
                  key={s.id}
                  className={`block w-full rounded-lg border px-3 py-2 text-left text-xs ${
                    s.id === sessionId
                      ? "border-cyan-700 bg-cyan-500/10 text-cyan-200"
                      : "border-slate-800 text-slate-400 hover:border-slate-600"
                }`}
                  onClick={() => void resumeSession(s.id)}
                >
                  <div className="font-medium">{s.title}</div>
                  <div className="mono text-slate-600">{s.id.slice(0, 8)}</div>
                </button>
              ))}
          </div>
        </section>

        <section className="card">
          <h2 className="mb-2 font-semibold text-slate-200">Artifacts</h2>
          <div className="space-y-2">
            {(artifacts.data ?? []).length === 0 && (
              <p className="text-xs text-slate-500">Reports, plots and trajectories appear here.</p>
            )}
            {(artifacts.data ?? []).map((a) => (
              <div key={a.id} className="rounded-lg border border-slate-800 bg-slate-950/50 p-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="badge bg-slate-800 text-slate-300">{a.kind}</span>
                  <a
                    href={artifactUrl(a.id)}
                    target="_blank"
                    rel="noreferrer"
                    className="truncate text-xs text-cyan-400 hover:underline"
                  >
                    {a.filename}
                  </a>
                </div>
                <div className="mt-1 flex items-center justify-between text-[10px] text-slate-600">
                  <span className="mono">sha256 {a.sha256.slice(0, 12)}…</span>
                  <span>{a.size_bytes} B</span>
                </div>
                {a.filename.endsWith(".png") && <ArtifactImage id={a.id} alt={a.filename} />}
              </div>
            ))}
          </div>
        </section>

        {sessionId && (
          <section className="card">
            <h2 className="mb-2 font-semibold text-slate-200">Shared research state</h2>
            <pre className="mono max-h-72 overflow-auto rounded bg-slate-950/70 p-2 text-[11px] text-slate-400">
              {JSON.stringify(session.data?.state ?? {}, null, 2).slice(0, 4000)}
            </pre>
          </section>
        )}
      </div>
    </div>
  );
}

/** Lightweight session cache fetched per project (memoized outside query layer). */
const sessionCache = new Map<string, Session[]>();
function useSessionListCache(projects: Project[]): Session[] {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      for (const p of projects) {
        if (sessionCache.has(p.id)) continue;
        try {
          const detail = await api<Project & { sessions: Session[] }>(`/api/projects/${p.id}`);
          sessionCache.set(p.id, detail.sessions ?? []);
        } catch {
          sessionCache.set(p.id, []);
        }
      }
      if (!cancelled) setTick((t) => t + 1);
    })();
    return () => {
      cancelled = true;
    };
  }, [projects]);
  void tick;
  return projects.flatMap((p) => sessionCache.get(p.id) ?? []);
}

function ArtifactImage({ id, alt }: { id: string; alt: string }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let revoked: string | null = null;
    void fetch(`/api/artifacts/${id}/download`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    })
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (!blob) return;
        revoked = URL.createObjectURL(blob);
        setUrl(revoked);
      })
      .catch(() => undefined);
    return () => {
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [id]);
  if (!url) return null;
  return <img src={url} alt={alt} className="mt-2 rounded" />;
}