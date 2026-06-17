"""Tests for scorecard aggregation."""

from mcp_govcheck import score
from mcp_govcheck.types import CheckResult, Finding, Severity


def _finding(result, severity=Severity.MEDIUM, refs=()):
    return Finding(
        check_id="c",
        tool="t",
        result=result,
        severity=severity,
        principle="p",
        control_refs=tuple(refs),
    )


def _scorecard(findings):
    return score.build_scorecard("demo", findings, tools_scanned=1)


def test_pass_rate_ignores_not_applicable():
    sc = _scorecard([
        _finding(CheckResult.PASS),
        _finding(CheckResult.FAIL),
        _finding(CheckResult.NOT_APPLICABLE),
    ])
    assert sc.pass_rate == 0.5  # 1 pass / 2 applicable


def test_pass_rate_is_one_when_nothing_applies():
    sc = _scorecard([_finding(CheckResult.NOT_APPLICABLE)])
    assert sc.pass_rate == 1.0


def test_severity_breakdown_zero_filled():
    sc = _scorecard([
        _finding(CheckResult.FAIL, Severity.HIGH),
        _finding(CheckResult.FAIL, Severity.HIGH),
        _finding(CheckResult.FAIL, Severity.LOW),
        _finding(CheckResult.PASS, Severity.HIGH),  # pass shouldn't count
    ])
    b = score.severity_breakdown(sc)
    assert b[Severity.HIGH] == 2
    assert b[Severity.LOW] == 1
    assert b[Severity.MEDIUM] == 0


def test_failed_controls_collects_refs_from_failures_only():
    sc = _scorecard([
        _finding(CheckResult.FAIL, refs=["ISO27001:A.8.2"]),
        _finding(CheckResult.PASS, refs=["SOC2:CC6.1"]),
    ])
    assert score.failed_controls(sc) == {"ISO27001:A.8.2"}


def test_has_high_failures():
    assert score.has_high_failures(_scorecard([_finding(CheckResult.FAIL, Severity.HIGH)]))
    assert not score.has_high_failures(_scorecard([_finding(CheckResult.FAIL, Severity.LOW)]))


def test_summary_counts():
    sc = _scorecard([
        _finding(CheckResult.PASS),
        _finding(CheckResult.FAIL),
        _finding(CheckResult.NOT_APPLICABLE),
    ])
    c = score.summary_counts(sc)
    assert c["passed"] == 1
    assert c["failed"] == 1
    assert c["not_applicable"] == 1
    assert c["applicable"] == 2
    assert c["checks_total"] == 3
