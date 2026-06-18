"""Render scorecards and evidence packs to markdown and JSON.

Pure formatting — no I/O, no clocks. The CLI passes the rendered strings to
stdout or files. JSON output is deterministic (sorted keys) so it diffs cleanly
and can be snapshot-tested.
"""

from __future__ import annotations

import json
from typing import Any

from . import controls, score
from .types import EvidencePack, EvidenceStatus, Scorecard, Severity

_SEVERITY_ORDER = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}


def _cell(value: str) -> str:
    """Escape a value for safe interpolation into a markdown table cell.

    Untrusted text (tool names, claims, details, exceptions) can contain a
    literal ``|`` that would otherwise inject a spurious column and corrupt the
    deterministic, snapshot-tested table. Every dynamic cell goes through here.
    """
    return value.replace("|", "\\|")


# --- Scorecard -------------------------------------------------------------

def scorecard_to_dict(sc: Scorecard) -> dict[str, Any]:
    counts = score.summary_counts(sc)
    return {
        "target": sc.target,
        "summary": {
            **counts,
            "pass_rate": round(sc.pass_rate, 4),
            "high_failures": score.severity_breakdown(sc)[Severity.HIGH],
        },
        "failed_controls": sorted(score.failed_controls(sc)),
        "findings": [
            {
                "check_id": f.check_id,
                "tool": f.tool,
                "result": f.result.value,
                "severity": f.severity.value,
                "principle": f.principle,
                "control_refs": list(f.control_refs),
                "detail": f.detail,
            }
            for f in sc.findings
        ],
    }


def scorecard_to_json(sc: Scorecard) -> str:
    return json.dumps(scorecard_to_dict(sc), indent=2, sort_keys=True)


def scorecard_to_markdown(sc: Scorecard) -> str:
    counts = score.summary_counts(sc)
    sev = score.severity_breakdown(sc)
    lines = [
        f"# Governance scorecard — `{sc.target}`",
        "",
        f"**Pass rate:** {sc.pass_rate:.0%} "
        f"({counts['passed']}/{counts['applicable']} applicable checks) · "
        f"**Tools scanned:** {counts['tools_scanned']}",
        "",
        f"Failures by severity — high: {sev[Severity.HIGH]} · "
        f"medium: {sev[Severity.MEDIUM]} · low: {sev[Severity.LOW]}",
        "",
    ]

    failures = sorted(
        sc.failures, key=lambda f: (_SEVERITY_ORDER[f.severity], f.tool, f.check_id)
    )
    if failures:
        lines += ["## Findings", "", "| Severity | Tool | Check | Controls | Detail |",
                  "|---|---|---|---|---|"]
        for f in failures:
            refs = ", ".join(f.control_refs) or "—"
            lines.append(
                f"| {f.severity.value} | `{_cell(f.tool)}` | {_cell(f.check_id)} | "
                f"{_cell(refs)} | {_cell(f.detail)} |"
            )
        lines.append("")

    failed = sorted(score.failed_controls(sc))
    if failed:
        lines += ["## Implicated controls", ""]
        for ref in failed:
            ctrl = controls.get_control(ref)
            lines.append(f"- **{ref}** — {ctrl.title} ({ctrl.framework})")
        lines.append("")

    if not failures:
        lines += ["✅ No governance failures found.", ""]

    return "\n".join(lines)


# --- EvidencePack ----------------------------------------------------------

def evidence_to_dict(pack: EvidencePack) -> dict[str, Any]:
    return {
        "source": pack.source,
        "summary": {
            "calls_examined": pack.calls_examined,
            "controls_total": len(pack.evidence),
            "satisfied": len(pack.satisfied),
            "violated": len(pack.violated),
            "no_evidence": sum(
                1 for e in pack.evidence if e.status is EvidenceStatus.NO_EVIDENCE
            ),
        },
        "evidence": [
            {
                "control_ref": e.control_ref,
                "control_title": controls.get_control(e.control_ref).title,
                "status": e.status.value,
                "claim": e.claim,
                "evidence_refs": list(e.evidence_refs),
                "exceptions": list(e.exceptions),
            }
            for e in pack.evidence
        ],
    }


def evidence_to_json(pack: EvidencePack) -> str:
    return json.dumps(evidence_to_dict(pack), indent=2, sort_keys=True)


def evidence_to_markdown(pack: EvidencePack) -> str:
    lines = [
        f"# Compliance evidence — `{pack.source}`",
        "",
        f"**Calls examined:** {pack.calls_examined} · "
        f"satisfied: {len(pack.satisfied)} · violated: {len(pack.violated)}",
        "",
        "| Control | Status | Claim | Evidence | Exceptions |",
        "|---|---|---|---|---|",
    ]
    icon = {
        EvidenceStatus.SATISFIED: "✅ satisfied",
        EvidenceStatus.VIOLATED: "❌ violated",
        EvidenceStatus.NO_EVIDENCE: "— no evidence",
    }
    for e in pack.evidence:
        ctrl = controls.get_control(e.control_ref)
        refs = _cell(", ".join(e.evidence_refs)) or "—"
        exc = _cell("; ".join(e.exceptions)) or "—"
        lines.append(
            f"| **{_cell(e.control_ref)}** {_cell(ctrl.title)} | {icon[e.status]} | "
            f"{_cell(e.claim)} | {refs} | {exc} |"
        )
    lines.append("")
    return "\n".join(lines)
