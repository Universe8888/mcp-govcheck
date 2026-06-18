"""Core data types for mcp-govcheck.

Pure data — no MCP dependency, no I/O. Everything the rubric/score/evidence
engines pass around is defined here so each module can be reasoned about and
tested in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    """Severity of a governance finding."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CheckResult(StrEnum):
    """Outcome of evaluating one rubric check against one tool."""

    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class EvidenceStatus(StrEnum):
    """Whether a control is supported (satisfied) or contradicted (violated)
    by a tool-call log during `attest`."""

    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NO_EVIDENCE = "no_evidence"


@dataclass(frozen=True)
class Control:
    """A single governance control in the canonical catalog.

    `ref` is the stable id used everywhere (e.g. "ISO27001:A.8.2"); it is the
    only thing other modules reference — never the human title.
    """

    ref: str
    framework: str  # e.g. "ISO27001", "SOC2"
    title: str


@dataclass(frozen=True)
class ToolSpec:
    """A tool exposed by an MCP server, as seen at design time.

    `params` maps parameter name -> a lightweight schema dict (at minimum
    {"type": ...}; may carry "description", "default", etc.). This is what the
    rubric inspects — we never execute the tool.
    """

    name: str
    description: str = ""
    params: dict[str, dict[str, Any]] = field(default_factory=dict)

    def param_names(self) -> set[str]:
        return set(self.params)


@dataclass(frozen=True)
class ToolCall:
    """One recorded invocation from a tool-call log, consumed by `attest`."""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    confirmed: bool = False
    outcome: str = "ok"  # "ok" | "denied" | "error"
    ts: str | None = None
    raw_index: int = -1  # 1-based source-log line number, for evidence_refs (log#<n>)


@dataclass(frozen=True)
class Finding:
    """Result of one rubric check applied to one tool (from `scan`)."""

    check_id: str
    tool: str
    result: CheckResult
    severity: Severity
    principle: str
    control_refs: tuple[str, ...]
    detail: str = ""


@dataclass
class Scorecard:
    """Aggregated `scan` result over all tools and checks."""

    target: str
    findings: list[Finding] = field(default_factory=list)
    tools_scanned: int = 0

    @property
    def applicable(self) -> list[Finding]:
        return [f for f in self.findings if f.result is not CheckResult.NOT_APPLICABLE]

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.result is CheckResult.FAIL]

    @property
    def passes(self) -> list[Finding]:
        return [f for f in self.findings if f.result is CheckResult.PASS]

    @property
    def pass_rate(self) -> float:
        """Fraction of *applicable* checks that passed (1.0 if none apply)."""
        applicable = self.applicable
        if not applicable:
            return 1.0
        return len(self.passes) / len(applicable)

    def failures_by_severity(self, severity: Severity) -> list[Finding]:
        return [f for f in self.failures if f.severity is severity]


@dataclass
class ControlEvidence:
    """Evidence for a single control, derived from a tool-call log (`attest`)."""

    control_ref: str
    status: EvidenceStatus
    claim: str
    evidence_refs: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)


@dataclass
class EvidencePack:
    """Control-mapped evidence derived from a tool-call log."""

    source: str
    evidence: list[ControlEvidence] = field(default_factory=list)
    calls_examined: int = 0

    @property
    def satisfied(self) -> list[ControlEvidence]:
        return [e for e in self.evidence if e.status is EvidenceStatus.SATISFIED]

    @property
    def violated(self) -> list[ControlEvidence]:
        return [e for e in self.evidence if e.status is EvidenceStatus.VIOLATED]
