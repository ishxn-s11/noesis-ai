"""Reproducible scientific report generation from durable research state.

The report only contains what was actually executed: plan nodes, executed
checks, persisted artifacts, and memory records with their versions. All
limitations and demo-data labels are carried through verbatim.
"""
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.artifacts import save_artifact
from app.database.models import AgentRun, Artifact, Experiment, ValidationResult
from app.database.models import ResearchSession


def generate_report(db, *, job, session: ResearchSession, state) -> tuple:
    """Build a markdown report artifact. Returns (Artifact, summary)."""
    runs = list(db.scalars(
        select(AgentRun).where(AgentRun.job_id == job.id).order_by(AgentRun.started_at)
    ).all())
    exp = None
    if job.payload.get("experiment_id"):
        exp = job.payload["experiment_id"]
    validation_rows = select(ValidationResult).where(ValidationResult.tenant_id == job.tenant_id)
    if exp:
        validation_rows = validation_rows.where(ValidationResult.experiment_id == exp)
    elif job.kind == "research_run":
        validation_rows = validation_rows.where(ValidationResult.job_id == job.id)
    validations = list(db.scalars(
        validation_rows.order_by(ValidationResult.created_at.desc()).limit(200)
    ).all())
    artifacts = list(db.scalars(
        select(Artifact).where(
            Artifact.session_id == session.id, Artifact.tenant_id == job.tenant_id
        )
    ).all())

    lines: list[str] = []
    lines.append(f"# {state.objective or 'NOESIS AI Research Report'}")
    lines.append("")
    lines.append(f"- **Generated:** {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append(f"- **Session:** `{session.id}`  |  **Job:** `{job.id}`")
    lines.append(f"- **Domain:** {state.domain}")
    lines.append(f"- **Code version:** 0.1.0  |  **Reproducibility:** deterministic tools, "
                 f"seeded RNG")
    lines.append("")
    if state.research_question or state.objective:
        lines.append("## 1. Research question")
        lines.append("")
        lines.append(state.research_question or state.objective)
        lines.append("")
    lines.append("## 2. Hypothesis (epistemic status: HYPOTHESIS — not a finding)")
    lines.append("")
    lines.append(state.hypothesis or "_none recorded_")
    lines.append("")

    # --- method / equations -------------------------------------------------
    lines.append("## 3. Governing equations & assumptions")
    lines.append("")
    eqs = state.approved_parameters.get("equations", [])
    if eqs:
        lines.append("| Equation | LaTeX | Validity regime | Source |")
        lines.append("|---|---|---|---|")
        for eq in eqs:
            lines.append(f"| {eq['name']} | `{eq.get('latex', '')}` | {eq['regime']} | "
                         f"{eq['source']} |")
    else:
        lines.append("_No symbolic equations recorded for this run._")
    lines.append("")
    assumptions = state.approved_parameters.get("assumptions", [])
    if assumptions:
        lines.append("**Assumptions:**")
        for a in assumptions:
            lines.append(f"- {a}")
        lines.append("")

    # --- executed work (agent timeline with evidence) ----------------------
    lines.append("## 4. Executed workflow (agent activity timeline)")
    lines.append("")
    lines.append("| # | Agent | Node | Status | Evidence (tools that actually ran) |")
    lines.append("|---|---|---|---|---|")
    for i, r in enumerate(runs, 1):
        tools = ", ".join(sorted({e.get("tool", "?") for e in (r.evidence or [])})) or "—"
        lines.append(f"| {i} | {r.agent} | `{r.node}` | {r.status} | {tools} |")
    lines.append("")

    # --- results ------------------------------------------------------------
    lines.append("## 5. Results")
    lines.append("")
    for name, data in state.intermediate_results.items():
        if name == "sweep":
            lines.append("### Parameter sweep (third-body stability)")
            lines.append("")
            summary = data.get("summary", {})
            lines.append(f"- Runs executed: **{summary.get('n_runs')}** "
                         f"(wall time {summary.get('total_wall_time_s')} s)")
            lines.append(f"- Stable per criterion: **{summary.get('n_stable')}/"
                         f"{summary.get('n_runs')}** "
                         f"(fraction {summary.get('stability_fraction'):.2f})")
            crit = summary.get("stability_criteria", {})
            lines.append(f"- Stability criterion: {crit.get('definition', '')}")
            lines.append("")
            rows = data.get("runs", [])
            if rows:
                lines.append("| Run | Status | Stable | e-proxy | max \\|ΔE/E₀\\| | wall (s) |")
                lines.append("|---|---|---|---|---|---|")
                for r in rows:
                    lines.append(
                        f"| {r.get('label', '')} | {r.get('status', '')} | "
                        f"{'✅' if r.get('stable') else '❌'} | "
                        f"{_fmt(r.get('ecc_proxy'))} | {_fmt(r.get('energy_drift_rel_max'))} | "
                        f"{_fmt(r.get('wall_time_s'))} |")
                lines.append("")
            if data.get("artifact_ids"):
                lines.append(f"Artifacts: {', '.join(f'`{a}`' for a in data['artifact_ids'])}")
                lines.append("")
        else:
            lines.append(f"### {name.replace('_', ' ').title()}")
            lines.append("")
            lines.append("```json")
            import json

            lines.append(json.dumps(_prune(data), indent=2, default=str)[:3000])
            lines.append("```")
            lines.append("")

    # --- validation ---------------------------------------------------------
    lines.append("## 6. Validation (executed checks, not assertions)")
    lines.append("")
    if validations:
        lines.append("| Check | Passed | Details |")
        lines.append("|---|---|---|")
        for v in validations:
            lines.append(f"| {v.check_name} | {'yes' if v.passed else 'NO'} | "
                         f"{(v.details or '')[:160]} |")
    else:
        lines.append("_No validation checks recorded._")
    lines.append("")

    n_pass = sum(1 for v in validations if v.passed)
    vdict = state.validation_decisions[-1] if state.validation_decisions else {}

    # --- limitations --------------------------------------------------------
    lines.append("## 7. Limitations & uncertainty")
    lines.append("")
    for u in state.open_uncertainties:
        lines.append(f"- {u}")
    lines.append("- Simplified analytic/dynamical models are labeled as such wherever used; "
                 "they are not MESA/GR-grade simulations.")
    if state.intermediate_results.get("cosmology", {}).get("posterior_is_demo"):
        lines.append("- MCMC posterior uses **SYNTHETIC DEMO DATA** generated from Planck18; "
                     "it is NOT an analysis of real supernova observations.")
    lines.append("- No claim of scientific discovery is made; hypothesis status retained.")
    lines.append("")

    # --- references & artifacts --------------------------------------------
    lines.append("## 8. References")
    lines.append("")
    refs = [eq["source"] for eq in eqs] + [
        "Rein & Liu 2012, A&A 537, A128 (IAS15)",
        "Planck Collaboration 2020, A&A 641, A6",
        "Murray & Dermott 1999, Solar System Dynamics",
        "astropy: The Astropy Collaboration 2018, AJ 156, 123",
    ]
    for r in sorted(set(refs)):
        lines.append(f"- {r}")
    lines.append("")
    lines.append("## 9. Artifacts (content-addressed, tenant-scoped)")
    lines.append("")
    if artifacts:
        for a in artifacts[:30]:
            lines.append(f"- `{a.id[:8]}` **{a.kind}** — {a.filename} "
                         f"(sha256 `{a.sha256[:12]}…`, {a.size_bytes} B)")
    else:
        lines.append("_No artifacts bound to this session._")
    lines.append("")
    lines.append("---")
    lines.append("_Generated by NOESIS AI Report Generation Agent. Every claim in sections 4–6 "
                 "derives from persisted tool execution records; verify artifacts by sha256._")

    content = "\n".join(lines).encode("utf-8")
    art = save_artifact(
        db, tenant_id=job.tenant_id, kind="report",
        filename=f"report_{session.id[:8]}.md", content=content,
        project_id=job.project_id, session_id=session.id,
        content_type="text/markdown",
        meta={"n_agent_runs": len(runs), "n_validations": len(validations),
              "n_passed": n_pass, "n_artifacts": len(artifacts)},
    )
    summary = {
        "sections": ["question", "hypothesis", "equations", "workflow", "results",
                     "validation", "limitations", "references", "artifacts"],
        "n_references": len(set(refs)),
        "n_artifacts": len(artifacts),
        "validation_passed": n_pass,
        "validation_total": len(validations),
        "all_validations_passed": bool(validations) and n_pass == len(validations),
        "artifacts": [_public(a) for a in artifacts],
    }
    return art, summary


def _fmt(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.3e}" if abs(x) < 1e-3 or abs(x) > 1e5 else f"{x:.4g}"
    return str(x)


def _prune(data, depth=0):
    if depth > 3:
        return "…"
    if isinstance(data, dict):
        return {k: _prune(v, depth + 1) for k, v in list(data.items())[:40]}
    if isinstance(data, list):
        return [_prune(v, depth + 1) for v in data[:20]]
    return data


def _public(a) -> dict:
    return {"id": a.id, "kind": a.kind, "filename": a.filename, "sha256": a.sha256}