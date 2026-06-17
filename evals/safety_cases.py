"""Adversarial safety properties that MUST hold.

These are not accuracy metrics — they are invariants. If any returns a failure
message, the eval run fails (non-zero exit). They encode the guarantees the
tool would be worthless without:

  S1  A destructive tool with no confirmation parameter is ALWAYS flagged
      (no rubric ordering / glob quirk lets it slip through).
  S2  `attest` NEVER reports a control SATISFIED when the log contains a
      violating call (one unconfirmed destructive call flips it to VIOLATED).
  S3  Evidence is never silently dropped: a violating call always appears in
      some ControlEvidence.exceptions.
  S4  Control mapping is total: every control_ref a rubric/policy emits is
      resolvable in the canonical catalog (no dangling references).
  S5  A forbidden 'force' escape-hatch parameter is ALWAYS flagged.
"""

from __future__ import annotations

from mcp_govcheck import controls
from mcp_govcheck.evidence import DEFAULT_POLICIES, attest
from mcp_govcheck.types import CheckResult, EvidenceStatus, ToolCall, ToolSpec


def _findings_for(rubric, tool: ToolSpec, check_id: str):
    return [f for f in rubric.evaluate([tool]) if f.check_id == check_id]


def s1_destructive_without_confirm_always_flagged(rubric) -> str | None:
    # Vary the destructive tool name across delete_/purge_ to dodge ordering luck.
    confirm_checks = ("destructive-requires-confirmation", "purge-requires-confirmation")
    for name in ("delete_x", "delete_everything", "purge_db"):
        tool = ToolSpec(
            name=name, description="Destructive op.", params={"id": {"type": "integer"}}
        )
        findings = [
            f
            for f in rubric.evaluate([tool])
            if f.check_id in confirm_checks and f.result is CheckResult.FAIL
        ]
        if not findings:
            return f"S1 FAIL: destructive tool {name!r} not flagged for missing confirmation"
    return None


def s2_violation_blocks_satisfied(_rubric) -> str | None:
    calls = [
        ToolCall(tool="delete_asset", confirmed=True, raw_index=0),
        ToolCall(tool="delete_asset", confirmed=False, raw_index=1),  # violation
    ]
    pack = attest("eval", calls, DEFAULT_POLICIES)
    for ev in pack.evidence:
        if ev.claim.startswith("every destructive") and ev.status is EvidenceStatus.SATISFIED:
            return "S2 FAIL: control reported SATISFIED despite an unconfirmed destructive call"
    return None


def s3_violation_recorded_as_exception(_rubric) -> str | None:
    calls = [ToolCall(tool="delete_asset", confirmed=False, raw_index=7)]
    pack = attest("eval", calls, DEFAULT_POLICIES)
    if not any("log#7" in exc for ev in pack.evidence for exc in ev.exceptions):
        return "S3 FAIL: violating call log#7 not recorded in any exceptions list"
    return None


def s4_control_mapping_is_total(rubric) -> str | None:
    refs: set[str] = set()
    for check in rubric.checks:
        refs.update(check.control_refs)
    for policy in DEFAULT_POLICIES:
        refs.update(policy.control_refs)
    unknown = controls.validate_refs(list(refs))
    if unknown:
        return f"S4 FAIL: rubric/policies reference unknown controls {unknown}"
    return None


def s5_force_escape_hatch_always_flagged(rubric) -> str | None:
    tool = ToolSpec(name="do_thing", description="Does a thing.",
                    params={"force": {"type": "boolean", "description": "skip"}})
    findings = _findings_for(rubric, tool, "no-force-escape-hatch")
    if not findings or findings[0].result is not CheckResult.FAIL:
        return "S5 FAIL: 'force' escape-hatch parameter was not flagged"
    return None


SAFETY_CASES = [
    s1_destructive_without_confirm_always_flagged,
    s2_violation_blocks_satisfied,
    s3_violation_recorded_as_exception,
    s4_control_mapping_is_total,
    s5_force_escape_hatch_always_flagged,
]


def run_safety(rubric) -> list[str]:
    """Return a list of failure messages (empty == all safety properties hold)."""
    failures: list[str] = []
    for case in SAFETY_CASES:
        msg = case(rubric)
        if msg:
            failures.append(msg)
    return failures
