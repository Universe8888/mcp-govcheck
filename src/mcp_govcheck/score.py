"""Aggregate rubric findings into a Scorecard.

Thin layer over :class:`~mcp_govcheck.types.Scorecard` (which carries the
pass/fail/pass-rate logic) plus the severity and per-control rollups the
report and CLI need.
"""

from __future__ import annotations

from .types import CheckResult, Finding, Scorecard, Severity


def build_scorecard(target: str, findings: list[Finding], tools_scanned: int) -> Scorecard:
    return Scorecard(target=target, findings=list(findings), tools_scanned=tools_scanned)


def severity_breakdown(scorecard: Scorecard) -> dict[Severity, int]:
    """Count of FAIL findings per severity (all severities present, zero-filled)."""
    counts = {sev: 0 for sev in Severity}
    for finding in scorecard.failures:
        counts[finding.severity] += 1
    return counts


def failed_controls(scorecard: Scorecard) -> set[str]:
    """Distinct control refs implicated by at least one FAIL finding."""
    refs: set[str] = set()
    for finding in scorecard.failures:
        refs.update(finding.control_refs)
    return refs


def has_high_failures(scorecard: Scorecard) -> bool:
    return any(f.severity is Severity.HIGH for f in scorecard.failures)


def summary_counts(scorecard: Scorecard) -> dict[str, int]:
    """Flat counts for JSON/CLI output."""
    return {
        "tools_scanned": scorecard.tools_scanned,
        "checks_total": len(scorecard.findings),
        "applicable": len(scorecard.applicable),
        "passed": len(scorecard.passes),
        "failed": len(scorecard.failures),
        "not_applicable": sum(
            1 for f in scorecard.findings if f.result is CheckResult.NOT_APPLICABLE
        ),
    }
