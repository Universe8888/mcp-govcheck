"""Tests for `attest` — control-mapped evidence from a tool-call log."""

import pytest

from mcp_govcheck.evidence import (
    DEFAULT_POLICIES,
    EvidencePolicy,
    attest,
    load_calls,
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


def test_raw_index_is_true_source_line_with_blank_lines(tmp_path):
    # raw_index must be the actual file line number (1-based) so the `log#<n>`
    # evidence citation points at the real offending line — even when blank
    # lines precede it. A non-blank call counter would silently mis-cite.
    log = tmp_path / "calls.jsonl"
    log.write_text(
        '{"tool": "get_asset", "outcome": "ok"}\n'
        "\n"  # blank line — must not shift the citation
        '{"tool": "delete_asset", "confirmed": false, "outcome": "ok"}\n',
        encoding="utf-8",
    )
    calls = load_calls(log)
    # The delete call is physically on line 3 of the file.
    delete_call = next(c for c in calls if c.tool == "delete_asset")
    assert delete_call.raw_index == 3

    pack = attest(str(log), calls, DEFAULT_POLICIES)
    assert any("log#3" in exc for e in pack.evidence for exc in e.exceptions)


def test_raw_index_matches_malformed_line_numbering(tmp_path):
    # The `log#<n>` citation and the malformed-line error must use the SAME
    # 1-based line numbering, so the two never disagree about "line N".
    good = tmp_path / "good.jsonl"
    good.write_text('{"tool": "get_asset"}\n', encoding="utf-8")
    assert load_calls(good)[0].raw_index == 1  # first line is line 1, not 0

    bad = tmp_path / "bad.jsonl"
    bad.write_text("not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r":1:"):  # also reports line 1
        load_calls(bad)


def test_all_calls_logged_flags_missing_tool_name():
    calls = [_call("", idx=0), _call("get_asset", idx=1)]
    log_policy = EvidencePolicy(
        id="logged", kind="all_calls_logged",
        control_refs=("ISO27001:A.8.15",), claim="logged",
    )
    pack = attest("log", calls, [log_policy])
    assert pack.evidence[0].status is EvidenceStatus.VIOLATED
