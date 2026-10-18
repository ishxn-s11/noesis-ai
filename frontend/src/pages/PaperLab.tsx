import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, downloadArtifact, subscribeJobEvents } from "../api";
import { ExplainText } from "../components/Explain";

interface PaperMeta {
  kind: string;
  id: string;
  url: string;
  title: string;
  authors: string[];
  abstract: string;
  published: string;
  source: string;
}
interface Quantity {
  kind: string;
  value: number;
  unit: string;
  snippet: string;
}
interface RunRow {
  proposal_id: string;
  engine: string;
  label: string;
  justification: string;
  from_paper: Record<string, boolean>;
  status: string;
  headline?: Record<string, string | number>;
  detail?: Record<string, unknown>;
  fidelity?: string;
  error?: string;
}
interface ExplainSection {
  heading: string;
  body: string[];
}
interface Explanation {
  sections: ExplainSection[];
  glossary_terms: string[];
  verdict: string;
  n_executed_runs: number;
}
interface PaperState {
  paper?: PaperMeta;
  quantities?: Quantity[];
  subdomain?: string;
  extraction_scope?: string;
  runs?: RunRow[];
  explanation?: Explanation;
  findings_artifact_id?: string;
}
interface JobRow {
  id: string;
  status: string;
  error?: string;
  session_id?: string;
}
interface SessionState {
  task_graph?: Array<{ id: string; label: string; status: string; summary: string }>;
  intermediate_results?: { paper?: PaperState };
  validation_decisions?: Array<{
    all_passed?: boolean;
    checks?: Record<string, boolean>;
    tolerances?: string;
  }>;
}
interface Session {
  id: string;
  state: SessionState;
  state_version: number;
}
interface ArtifactRow {
  id: string;
  kind: string;
  filename: string;
  sha256: string;
}
interface MessageRow {
  id: string;
  agent: string;
  content: string;
}

const EXAMPLES = [
  "https://arxiv.org/abs/2401.12345",
  "https://arxiv.org/pdf/2303.08676v2",
  "https://doi.org/10.1051/0004-6361/201936871",
];

function nodeTone(status: string): string {
  if (status === "succeeded") return "bg-emerald-500/15 text-emerald-300";
  if (status === "failed" || status === "blocked") return "bg-rose-500/15 text-rose-300";
  if (status === "running") return "bg-cyan-500/15 text-cyan-300";
  return "bg-slate-500/15 text-slate-300";
}

export default function PaperLab() {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [jobId, setJobId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [liveEvents, setLiveEvents] = useState<Array<Record<string, unknown>>>([]);
  const logRef = useRef<HTMLDivElement>(null);

  const job = useQuery({
    queryKey: ["paper-job", jobId],
    queryFn: () => api<JobRow>(`/api/jobs/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: 1500,
  });

  const session = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api<Session>(`/api/sessions/${sessionId}`),
    enabled: Boolean(sessionId),
    refetchInterval: job.data?.status === "queued" || job.data?.status === "running" ? 2500 : false,
  });

  const artifacts = useQuery({
    queryKey: ["artifacts", sessionId],
    queryFn: () => api<ArtifactRow[]>(`/api/sessions/${sessionId}/artifacts`),
    enabled: Boolean(sessionId) && job.data?.status === "succeeded",
  });

  useEffect(() => {
    if (!jobId) return;
    const unsub = subscribeJobEvents(jobId, (evt) => {
      setLiveEvents((prev) => [...prev.slice(-80), evt]);
      if (evt.type === "graph_finished") {
        void session.refetch();
        void job.refetch();
      }
    });
    return unsub;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  useEffect(() => {
    logRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [liveEvents.length]);

  async function start() {
    setBusy(true);
    setError("");
    try {
      const resp = await api<{ job: JobRow; session_id: string }>(
        "/api/labs/paper/analyze",
        { method: "POST", body: JSON.stringify({ url: url.trim() }) },
      );
      setLiveEvents([]);
      setSessionId(resp.session_id);
      setJobId(resp.job.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const state = session.data?.state ?? {};
  const paperState: PaperState = state.intermediate_results?.paper ?? {};
  const paper = paperState.paper;
  const runs = paperState.runs ?? [];
  const quantities = paperState.quantities ?? [];
  const explanation = paperState.explanation;
  const validation = state.validation_decisions?.[state.validation_decisions.length - 1];
  const nodes = state.task_graph ?? [];
  const status = job.data?.status ?? "";
  const running = status === "queued" || status === "running";

  return (
    <div className="space-y-5">
      <header>
        <div className="eyebrow">Labs</div>
        <h1 className="display mt-2">Paper → Simulation</h1>
        <p className="mt-3 max-w-3xl text-[15px] leading-relaxed text-slate-300">
          Paste a research-paper link (arXiv or DOI). The agent orchestration pipeline fetches the
          metadata, extracts every quantitative claim verbatim from the abstract, maps the claims
          onto this platform's engines, executes them, cross-checks the results — and explains the
          outcome in plain language. Numbers come only from executed tools; failures are shown, not
          hidden.
        </p>
      </header>

      <section className="card space-y-3">
        <label className="block text-xs text-slate-400">
          Research paper link (arXiv abs/pdf or DOI)
          <input
            className="input mt-1"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://arxiv.org/abs/2401.12345"
            onKeyDown={(e) => {
              if (e.key === "Enter" && url.trim() && !busy) void start();
            }}
          />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-primary" onClick={() => void start()} disabled={busy || !url.trim()}>
            {busy ? "Starting…" : "▶ Process paper"}
          </button>
          {EXAMPLES.map((ex) => (
            <button key={ex} className="btn-ghost text-xs" onClick={() => setUrl(ex)}>
              {ex.includes("doi") ? "DOI example" : ex.split("/").slice(-2).join("/")}
            </button>
          ))}
          {jobId && (
            <span className="badge mono bg-cyan-500/15 text-cyan-300">
              job {jobId.slice(0, 8)} · {status || "…"}
            </span>
          )}
        </div>
        {error && <div className="text-sm text-rose-400">{error}</div>}
        {status === "failed" && (
          <div className="text-sm text-rose-400">
            Run failed: {job.data?.error || "see coordination timeline"}
          </div>
        )}
      </section>

      {nodes.length > 0 && (
        <section className="card">
          <h2 className="mb-3 font-semibold text-slate-200">Pipeline</h2>
          <div className="flex flex-wrap gap-2">
            {nodes.map((n, i) => (
              <div key={n.id} className="flex items-center gap-2">
                <div
                  className={`rounded-none border px-3 py-1.5 text-xs ${nodeTone(n.status)}`}
                  title={n.summary || n.label}
                >
                  <span className="mr-2 text-slate-500">{String(i + 1).padStart(2, "0")}</span>
                  {n.label}
                </div>
                {i < nodes.length - 1 && <span className="text-slate-600">→</span>}
              </div>
            ))}
          </div>
          {liveEvents.length > 0 && running && (
            <div
              ref={logRef}
              className="mt-3 max-h-40 space-y-1 overflow-y-auto border-t border-slate-800 pt-2 text-xs text-slate-400"
            >
              {liveEvents
                .filter((e) => String(e.type).startsWith("node_") || e.type === "graph_finished")
                .map((e, i) => (
                  <div key={i} className="mono">
                    [{String(e.type)}] {String(e.node ?? e.summary ?? "")}
                    {typeof e.summary === "string" && e.node ? ` — ${e.summary.slice(0, 140)}` : ""}
                  </div>
                ))}
            </div>
          )}
        </section>
      )}

      {paper && (
        <section className="card">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="font-semibold text-slate-200">Paper metadata</h2>
            <a
              className="border-b border-slate-100 text-xs hover:opacity-60"
              href={paper.url}
              target="_blank"
              rel="noreferrer"
            >
              {paper.source} ↗
            </a>
          </div>
          <div className="mt-2 text-sm font-semibold text-slate-100">{paper.title}</div>
          <div className="mt-1 text-xs text-slate-400">
            {(paper.authors ?? []).slice(0, 6).join(", ")}
            {(paper.authors ?? []).length > 6 && ` +${paper.authors.length - 6} more`}
            {paper.published ? ` · ${paper.published}` : ""}
          </div>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
            <ExplainText text={paper.abstract} />
          </p>
        </section>
      )}

      {quantities.length > 0 && (
        <section className="card">
          <h2 className="mb-1 font-semibold text-slate-200">
            Extracted quantitative claims ({quantities.length})
          </h2>
          <p className="mb-3 text-xs text-slate-500">
            {paperState.extraction_scope ?? "abstract only (regex; full text not parsed)"} — each
            number links to the literal text it came from.
          </p>
          <div className="space-y-2">
            {quantities.map((q, i) => (
              <div key={`${q.kind}-${i}`} className="rounded-none border border-slate-800 p-3">
                <div className="text-sm text-cyan-200">
                  {q.kind.replace(/_/g, " ")} ={" "}
                  <b>
                    {q.value} {q.unit}
                  </b>
                </div>
                <div className="mt-1 text-xs italic text-slate-500">“…{q.snippet}…”</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {runs.length > 0 && (
        <section className="card">
          <h2 className="mb-3 font-semibold text-slate-200">Executed simulations ({runs.length})</h2>
          <div className="space-y-3">
            {runs.map((r) => (
              <div
                key={r.proposal_id}
                className={`rounded-none border p-4 ${
                  r.status === "completed" ? "border-slate-700" : "border-rose-800"
                }`}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="text-sm font-semibold text-slate-200">{r.label}</div>
                  <span
                    className={`badge ${
                      r.status === "completed"
                        ? "bg-emerald-500/15 text-emerald-300"
                        : "bg-rose-500/15 text-rose-300"
                    }`}
                  >
                    {r.status}
                  </span>
                </div>
                <div className="mt-1 text-[11px] text-slate-500 mono">
                  {r.engine}
                  {r.fidelity ? ` · ${r.fidelity}` : ""}
                </div>
                <p className="mt-2 text-xs text-slate-400">
                  <ExplainText text={r.justification} />
                </p>
                {r.headline && (
                  <div className="mt-2 grid grid-cols-2 gap-2 text-xs md:grid-cols-3">
                    {Object.entries(r.headline).map(([k, v]) => (
                      <div key={k} className="border border-slate-800 p-2">
                        <div className="text-[10px] uppercase tracking-wide text-slate-500">
                          {k.replace(/_/g, " ")}
                        </div>
                        <div className="mt-0.5 font-semibold text-cyan-200">
                          {typeof v === "number" ? String(v) : v}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {r.status !== "completed" && r.error && (
                  <div className="mt-2 text-xs text-rose-400">{r.error}</div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {explanation && (
        <section className="card">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="font-semibold text-slate-200">Explanation</h2>
            <span
              className={`badge ${
                explanation.verdict === "validated"
                  ? "bg-emerald-500/15 text-emerald-300"
                  : "bg-amber-500/15 text-amber-300"
              }`}
            >
              {explanation.verdict}
            </span>
          </div>
          <div className="mt-3 space-y-4">
            {explanation.sections.map((s) => (
              <div key={s.heading}>
                <div className="eyebrow mb-1">{s.heading}</div>
                <div className="space-y-1.5 text-sm leading-relaxed text-slate-300">
                  {s.body.map((b, i) => (
                    <p key={i} className={s.heading.includes("Abstract") ? "text-xs italic" : ""}>
                      <ExplainText text={b} />
                    </p>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {validation?.checks && (
        <section className="card">
          <h2 className="mb-2 font-semibold text-slate-200">Validation checks</h2>
          <div className="flex flex-wrap gap-2">
            {Object.entries(validation.checks).map(([name, ok]) => (
              <span
                key={name}
                className={`badge ${
                  ok ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"
                }`}
              >
                {ok ? "✓" : "✗"} {name}
              </span>
            ))}
          </div>
          {validation.tolerances && (
            <div className="mt-2 text-[11px] text-slate-500">
              Tolerances: {validation.tolerances}
            </div>
          )}
        </section>
      )}

      {artifacts.data && artifacts.data.length > 0 && status === "succeeded" && (
        <section className="card">
          <h2 className="mb-2 font-semibold text-slate-200">Artifacts</h2>
          <div className="flex flex-wrap gap-2">
            {artifacts.data.map((a) => (
              <button
                key={a.id}
                className="btn-ghost text-xs"
                onClick={() => downloadArtifact(a.id, a.filename)}
                title={`sha256 ${a.sha256.slice(0, 12)}…`}
              >
                ⬇ {a.kind}: {a.filename}
              </button>
            ))}
          </div>
        </section>
      )}

      {sessionId && (
        <div className="flex flex-wrap gap-2">
          <Link to={`/coordination/${sessionId}`} className="btn-ghost text-xs">
            Coordination graph →
          </Link>
          <Link to={`/research/workspace/${sessionId}`} className="btn-ghost text-xs">
            Open in Research Workspace →
          </Link>
        </div>
      )}
    </div>
  );
}
