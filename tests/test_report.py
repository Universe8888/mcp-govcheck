"""Tests for markdown/JSON rendering of scorecards and evidence packs."""

import json

from mcp_govcheck import report, score
from mcp_govcheck.types import (
    CheckResult,
    ControlEvidence,
    EvidencePack,
    EvidenceStatus,
    Finding,
    Severity,
)


def _scorecard():
    findings = [
        Finding("destructive-requires-confirmation", "delete_asset", CheckResult.FAIL,
                Severity.HIGH, "human-in-the-loop", ("ISO27001:A.8.2",),
                "no confirmation parameter"),
        Finding("params-documented", "get_asset", CheckResult.PASS,
                Severity.MEDIUM, "auditability", ("ISO27001:A.8.15",), "ok"),
    ]
    return score.build_scorecard("demo-server", findings, tools_scanned=2)


def test_scorecard_json_is_valid_and_sorted():
    out = report.scorecard_to_json(_scorecard())
    data = json.loads(out)
    assert data["target"] == "demo-server"
    assert data["summary"]["failed"] == 1
    assert data["failed_controls"] == ["ISO27001:A.8.2"]
    # sorted keys → deterministic
    assert out == json.dumps(json.loads(out), indent=2, sort_keys=True)


def test_scorecard_markdown_lists_failure_and_control_title():
    md = report.scorecard_to_markdown(_scorecard())
    assert "Governance scorecard" in md
    assert "delete_asset" in md
    assert "Privileged access rights" in md  # resolved control title
    assert "Pass rate" in md


def test_clean_scorecard_says_no_failures():
    sc = score.build_scorecard("clean", [
        Finding("c", "t", CheckResult.PASS, Severity.LOW, "p", ())], 1)
    assert "No governance failures" in report.scorecard_to_markdown(sc)


def _pack():
    return EvidencePack(
        source="calls.jsonl",
        calls_examined=3,
        evidence=[
            ControlEvidence("ISO27001:A.8.2", EvidenceStatus.VIOLATED,
                            "destructive confirmed", [], ["log#2: no confirm"]),
            ControlEvidence("ISO27001:A.8.15", EvidenceStatus.SATISFIED,
                            "tool use logged", ["log#0", "log#1"], []),
        ],
    )


def test_evidence_json_valid_and_has_titles():
    data = json.loads(report.evidence_to_json(_pack()))
    assert data["summary"]["violated"] == 1
    titles = {e["control_ref"]: e["control_title"] for e in data["evidence"]}
    assert titles["ISO27001:A.8.15"] == "Logging"


def test_evidence_markdown_shows_status_icons():
    md = report.evidence_to_markdown(_pack())
    assert "violated" in md
    assert "satisfied" in md
    assert "log#2: no confirm" in md
