"""Tests for `attest` — control-mapped evidence from a tool-call log."""

import pytest

from mcp_govcheck.evidence import (
    DEFAULT_POLICIES,
    EvidencePolicy,
    attest,
)
from mcp_govcheck.types import EvidenceStatus, ToolCall


def _call(tool, confirmed=False, outcome="ok", idx=0, args=None):
    return ToolCall(tool=tool, args=args or {}, confirmed=confirmed, outcome=outcome, raw_index=idx)


CONFIRM_POLICY = EvidencePolicy(
    id="destructive-confirmed",
    kind="destructive_confirmed",
    tool_glob="delete_*",
    control_refs=("ISO27001:A.8.2", "SOC2:CC8.1"),
    claim="destructive calls confirmed",
)


def test_satisfied_when_all_destructive_confirmed():
    calls = [_call("delete_asset", confirmed=True, idx=0),
             _call("get_asset", idx=1)]
    pack = attest("log", calls, [CONFIRM_POLICY])
    assert all(e.status is EvidenceStatus.SATISFIED for e in pack.evidence)
    assert "log#0" in pack.evidence[0].evidence_refs


def test_one_unconfirmed_call_flips_to_violated():
    calls = [_call("delete_asset", confirmed=True, idx=0),
             _call("delete_asset", confirmed=False, idx=1)]
    pack = attest("log", calls, [CONFIRM_POLICY])
    assert all(e.status is EvidenceStatus.VIOLATED for e in pack.evidence)
    # the offending call is recorded as an exception, never dropped
    assert any("log#1" in exc for e in pack.evidence for exc in e.exceptions)


def test_denied_destructive_call_counts_as_compliant():
    calls = [_call("delete_asset", confirmed=False, outcome="denied", idx=0)]
    pack = attest("log", calls, [CONFIRM_POLICY])
    assert all(e.status is EvidenceStatus.SATISFIED for e in pack.evidence)


def test_no_relevant_calls_is_no_evidence():
    calls = [_call("get_asset", idx=0)]
    pack = attest("log", calls, [CONFIRM_POLICY])
    assert all(e.status is EvidenceStatus.NO_EVIDENCE for e in pack.evidence)


def test_one_control_evidence_per_mapped_control():
    calls = [_call("delete_asset", confirmed=True, idx=0)]
    pack = attest("log", calls, [CONFIRM_POLICY])
    refs = {e.control_ref for e in pack.evidence}
    assert refs == {"ISO27001:A.8.2", "SOC2:CC8.1"}


def test_unknown_kind_raises():
    bad = EvidencePolicy(id="x", kind="nope", control_refs=("ISO27001:A.8.2",), claim="c")
    with pytest.raises(ValueError, match="unknown kind"):
        attest("log", [_call("delete_asset")], [bad])


def test_unknown_control_ref_raises():
    bad = EvidencePolicy(
        id="x", kind="all_calls_logged", control_refs=("ISO27001:A.99.99",), claim="c"
    )
    with pytest.raises(ValueError, match="unknown control"):
        attest("log", [_call("get_asset")], [bad])


def test_default_policies_run_end_to_end():
    calls = [
        _call("delete_asset", confirmed=True, idx=0),
        _call("get_asset", idx=1),
        _call("delete_asset", confirmed=False, idx=2),  # violation
    ]
    pack = attest("log", calls, DEFAULT_POLICIES)
    assert pack.calls_examined == 3
    # destructive-confirmed controls should be violated; logging controls satisfied
    statuses = {e.control_ref: e.status for e in pack.evidence}
    assert statuses["ISO27001:A.8.2"] is EvidenceStatus.VIOLATED
    assert statuses["ISO27001:A.8.15"] is EvidenceStatus.SATISFIED


def test_all_calls_logged_flags_missing_tool_name():
    calls = [_call("", idx=0), _call("get_asset", idx=1)]
    log_policy = EvidencePolicy(
        id="logged", kind="all_calls_logged",
        control_refs=("ISO27001:A.8.15",), claim="logged",
    )
    pack = attest("log", calls, [log_policy])
    assert pack.evidence[0].status is EvidenceStatus.VIOLATED
