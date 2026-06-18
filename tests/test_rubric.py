"""Tests for the rubric engine (the heart of `scan`)."""

import pytest

from mcp_govcheck.rubric import Rubric, load_rubric_data
from mcp_govcheck.types import CheckResult, Severity, ToolSpec

# --- fixtures --------------------------------------------------------------

DELETE_NO_CONFIRM = ToolSpec(
    name="delete_asset",
    description="Delete an asset by id.",
    params={"asset_id": {"type": "integer", "description": "id"}},
)
DELETE_WITH_CONFIRM = ToolSpec(
    name="delete_asset",
    description="Delete an asset by id.",
    params={
        "asset_id": {"type": "integer", "description": "id"},
        "confirm": {"type": "boolean", "description": "must be true to proceed"},
    },
)
GET_ASSET = ToolSpec(
    name="get_asset",
    description="Read one asset.",
    params={"asset_id": {"type": "integer", "description": "id"}},
)
WILDCARD_WRITE = ToolSpec(
    name="update_asset",
    description="Update assets.",
    params={"scope": {"type": "string", "description": "which assets"},
            "force": {"type": "boolean", "description": "skip checks"}},
)

CONFIRM_RUBRIC = {
    "checks": [
        {
            "id": "destructive-requires-confirmation",
            "principle": "human-in-the-loop on destructive actions",
            "rule": "confirmation_required",
            "applies_to": {"tool": "delete_*"},
            "control_refs": ["ISO27001:A.8.2", "SOC2:CC6.1"],
            "severity": "high",
        }
    ]
}


def _rubric(data) -> Rubric:
    return load_rubric_data(data)


# --- applies_to / NOT_APPLICABLE -------------------------------------------

def test_check_not_applicable_when_tool_glob_does_not_match():
    r = _rubric(CONFIRM_RUBRIC)
    findings = r.evaluate([GET_ASSET])
    assert len(findings) == 1
    assert findings[0].result is CheckResult.NOT_APPLICABLE


def test_glob_match_is_case_insensitive():
    r = _rubric(CONFIRM_RUBRIC)
    upper = ToolSpec(name="DELETE_ASSET", description="x", params={})
    assert r.checks[0].applies_to(upper)


# --- confirmation_required --------------------------------------------------

def test_confirmation_required_fails_without_confirm_param():
    r = _rubric(CONFIRM_RUBRIC)
    f = r.evaluate([DELETE_NO_CONFIRM])[0]
    assert f.result is CheckResult.FAIL
    assert f.severity is Severity.HIGH
    assert f.control_refs == ("ISO27001:A.8.2", "SOC2:CC6.1")


def test_confirmation_required_passes_with_confirm_param():
    r = _rubric(CONFIRM_RUBRIC)
    f = r.evaluate([DELETE_WITH_CONFIRM])[0]
    assert f.result is CheckResult.PASS


def test_dry_run_does_not_satisfy_confirmation():
    # A `dry_run` preview flag is NOT a human-in-the-loop approval gate: it
    # defaults off and the destructive action still runs unattended when it is
    # False. It must not let `confirmation_required` report a false PASS.
    r = _rubric(CONFIRM_RUBRIC)
    dry_run_only = ToolSpec(
        name="delete_asset",
        description="Delete an asset by id.",
        params={
            "asset_id": {"type": "integer", "description": "id"},
            "dry_run": {"type": "boolean", "description": "preview only"},
        },
    )
    assert r.evaluate([dry_run_only])[0].result is CheckResult.FAIL


# --- forbidden_param (least privilege) -------------------------------------

def test_forbidden_param_flags_force_and_scope():
    data = {
        "checks": [
            {
                "id": "no-escape-hatches",
                "principle": "least privilege",
                "rule": "forbidden_param",
                "applies_to": {"tool": "*"},
                "control_refs": ["ISO27001:A.8.3", "SOC2:CC6.3"],
                "params": {"patterns": ["force", "scope"]},
            }
        ]
    }
    f = _rubric(data).evaluate([WILDCARD_WRITE])[0]
    assert f.result is CheckResult.FAIL


def test_forbidden_param_requires_patterns():
    data = {
        "checks": [
            {"id": "bad", "rule": "forbidden_param", "applies_to": {"tool": "*"}}
        ]
    }
    with pytest.raises(ValueError, match="non-empty 'patterns'"):
        _rubric(data).evaluate([GET_ASSET])


# --- description_required / params_documented ------------------------------

def test_description_required_fails_on_empty():
    data = {"checks": [{"id": "doc", "rule": "description_required"}]}
    tool = ToolSpec(name="x", description="  ", params={})
    assert _rubric(data).evaluate([tool])[0].result is CheckResult.FAIL


def test_params_documented_flags_undocumented_param():
    data = {"checks": [{"id": "p", "rule": "params_documented"}]}
    tool = ToolSpec(name="x", description="d", params={"a": {"type": "string"}})
    f = _rubric(data).evaluate([tool])[0]
    assert f.result is CheckResult.FAIL
    assert "a" in f.detail


# --- load-time validation (fail loud) --------------------------------------

def test_unknown_rule_raises():
    with pytest.raises(ValueError, match="unknown rule"):
        _rubric({"checks": [{"id": "x", "rule": "nope"}]})


def test_unknown_control_ref_raises():
    data = {"checks": [{"id": "x", "rule": "description_required",
                        "control_refs": ["ISO27001:A.99.99"]}]}
    with pytest.raises(ValueError, match="unknown control"):
        _rubric(data)


def test_duplicate_check_id_raises():
    data = {"checks": [
        {"id": "dup", "rule": "description_required"},
        {"id": "dup", "rule": "params_documented"},
    ]}
    with pytest.raises(ValueError, match="duplicate check id"):
        _rubric(data)


def test_empty_rubric_raises():
    with pytest.raises(ValueError, match="no checks"):
        _rubric({"checks": []})


def test_default_severity_applied():
    data = {"default_severity": "low",
            "checks": [{"id": "x", "rule": "description_required"}]}
    assert _rubric(data).checks[0].severity is Severity.LOW
