"""`attest`: turn a tool-call log into control-mapped compliance evidence.

Given a list of recorded :class:`~mcp_govcheck.types.ToolCall` objects and an
evidence policy, produce one :class:`~mcp_govcheck.types.ControlEvidence` per
control, stating whether the log *satisfies* or *violates* it and citing the
exact log lines as ``evidence_refs``.

Design rule (tested): a control is only ever reported SATISFIED if there is at
least one supporting call AND zero violating calls. A single violation flips it
to VIOLATED and records the offending calls as exceptions — evidence is never
silently dropped.

v1 ships two evidence policies, mirroring the rubric's two strongest checks:

* ``destructive_confirmed`` — every call to a destructive tool (name glob) must
  carry ``confirmed=True`` (or have been ``denied``). Maps to approval controls.
* ``all_calls_logged``      — presence of a non-empty, well-formed log itself is
  evidence that tool use is logged/monitored. Maps to logging controls.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path

from . import controls
from .types import ControlEvidence, EvidencePack, EvidenceStatus, ToolCall


def _glob(name: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(name.lower(), pattern.lower())


def _truthy(value: object) -> bool:
    """Coerce a JSON-ish value to bool (handles true/"true"/1)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def load_calls(path: str | Path) -> list[ToolCall]:
    """Parse a JSONL tool-call log into ToolCall objects.

    One JSON object per line. Tolerant of field-name variants:
    ``tool``/``tool_name``/``name`` and ``confirmed``/``confirm``. Each call
    keeps its true 1-based source line number (``raw_index``) so evidence can
    cite ``log#<n>`` at the exact line — the same numbering the malformed-line
    error uses. Blank lines are skipped (they do not shift the citation); a
    malformed line raises (fail loud — a broken audit log must not silently
    produce clean evidence).
    """
    calls: list[ToolCall] = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: invalid JSON in tool-call log") from exc
        tool = obj.get("tool") or obj.get("tool_name") or obj.get("name") or ""
        confirmed = _truthy(obj.get("confirmed", obj.get("confirm", False)))
        calls.append(
            ToolCall(
                tool=tool,
                args=obj.get("args", {}) or {},
                confirmed=confirmed,
                outcome=obj.get("outcome", "ok"),
                ts=obj.get("ts"),
                raw_index=lineno,
            )
        )
    return calls


def _ref(call: ToolCall) -> str:
    return f"log#{call.raw_index}"


@dataclass(frozen=True)
class EvidencePolicy:
    """One control-mapped assertion to evaluate against the call log."""

    id: str
    kind: str  # "destructive_confirmed" | "all_calls_logged"
    control_refs: tuple[str, ...]
    claim: str
    tool_glob: str = "*"


def _eval_destructive_confirmed(
    policy: EvidencePolicy, calls: list[ToolCall]
) -> tuple[EvidenceStatus, list[str], list[str]]:
    relevant = [c for c in calls if _glob(c.tool, policy.tool_glob)]
    if not relevant:
        return EvidenceStatus.NO_EVIDENCE, [], []

    supporting: list[str] = []
    exceptions: list[str] = []
    for call in relevant:
        # A destructive call is compliant if it was explicitly confirmed or was denied.
        if call.confirmed or call.outcome == "denied":
            supporting.append(_ref(call))
        else:
            exceptions.append(
                f"{_ref(call)}: {call.tool} executed without confirmation (outcome={call.outcome})"
            )

    if exceptions:
        return EvidenceStatus.VIOLATED, supporting, exceptions
    return EvidenceStatus.SATISFIED, supporting, []


def _eval_all_calls_logged(
    policy: EvidencePolicy, calls: list[ToolCall]
) -> tuple[EvidenceStatus, list[str], list[str]]:
    if not calls:
        return EvidenceStatus.NO_EVIDENCE, [], []
    # Malformed entries (no tool name) are exceptions to a clean logging claim.
    exceptions = [f"{_ref(c)}: log entry missing tool name" for c in calls if not c.tool]
    supporting = [_ref(c) for c in calls if c.tool]
    if exceptions:
        return EvidenceStatus.VIOLATED, supporting, exceptions
    return EvidenceStatus.SATISFIED, supporting, []


_EVALUATORS = {
    "destructive_confirmed": _eval_destructive_confirmed,
    "all_calls_logged": _eval_all_calls_logged,
}


def _evaluate_policy(policy: EvidencePolicy, calls: list[ToolCall]) -> list[ControlEvidence]:
    if policy.kind not in _EVALUATORS:
        raise ValueError(
            f"evidence policy {policy.id!r} uses unknown kind {policy.kind!r}. "
            f"Known kinds: {sorted(_EVALUATORS)}"
        )
    unknown = controls.validate_refs(list(policy.control_refs))
    if unknown:
        raise ValueError(f"policy {policy.id!r} references unknown control(s) {unknown}")

    status, refs, exceptions = _EVALUATORS[policy.kind](policy, calls)
    # One ControlEvidence per mapped control — never collapse multiple controls into one.
    return [
        ControlEvidence(
            control_ref=ref,
            status=status,
            claim=policy.claim,
            evidence_refs=list(refs),
            exceptions=list(exceptions),
        )
        for ref in policy.control_refs
    ]


def attest(
    source: str, calls: list[ToolCall], policies: list[EvidencePolicy]
) -> EvidencePack:
    """Build a control-mapped EvidencePack from a call log and policies."""
    evidence: list[ControlEvidence] = []
    for policy in policies:
        evidence.extend(_evaluate_policy(policy, calls))
    return EvidencePack(source=source, evidence=evidence, calls_examined=len(calls))


# Default policy set used by the CLI when none is supplied.
DEFAULT_POLICIES = [
    EvidencePolicy(
        id="destructive-confirmed",
        kind="destructive_confirmed",
        tool_glob="delete_*",
        control_refs=("ISO27001:A.8.2", "SOC2:CC8.1"),
        claim="every destructive tool call was confirmed or denied",
    ),
    EvidencePolicy(
        id="tool-use-logged",
        kind="all_calls_logged",
        control_refs=("ISO27001:A.8.15", "SOC2:CC7.2"),
        claim="all tool calls are captured in an auditable log",
    ),
]
