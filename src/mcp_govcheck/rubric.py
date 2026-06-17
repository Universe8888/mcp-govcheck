"""Governance rubric: declarative checks evaluated against tool specs.

A rubric is a list of *checks*. Each check selects the tools it applies to
(``applies_to.tool`` glob) and asserts one *rule* about each matching tool's
design. Evaluating a check against a tool yields a :class:`Finding`
(PASS / FAIL / NOT_APPLICABLE).

Rules vocabulary (v1) — each maps to a governance principle + control(s):

* ``confirmation_required`` — a destructive tool must expose a confirmation /
  approval parameter (human-in-the-loop).
* ``forbidden_param``       — a tool must NOT expose parameters matching given
  globs (least privilege: no ``force`` / wildcard-scope escape hatches).
* ``description_required``  — a tool must carry a non-empty description
  (auditability / documentation).
* ``params_documented``     — every declared parameter must be documented
  (auditability).

The rubric is validated on load: unknown rule names, unknown control refs, and
bad severities raise immediately (fail loud — never silently skip a check).
"""

from __future__ import annotations

import fnmatch
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import controls
from .types import CheckResult, Finding, Severity, ToolSpec

# Parameter-name globs treated as "confirmation / approval" gates by default.
DEFAULT_CONFIRMATION_PATTERNS = (
    "confirm",
    "confirmed",
    "confirm_*",
    "approve",
    "approv*",
    "ack",
    "acknowledge*",
    "dry_run",
)


def _glob(name: str, pattern: str) -> bool:
    """Case-insensitive glob match (deterministic across OSes)."""
    return fnmatch.fnmatchcase(name.lower(), pattern.lower())


def _any_param_matches(tool: ToolSpec, patterns: tuple[str, ...]) -> list[str]:
    """Return declared param names matching any pattern."""
    return [p for p in tool.param_names() if any(_glob(p, pat) for pat in patterns)]


# --- rule implementations: (tool, params) -> (passed, detail) --------------

def _rule_confirmation_required(tool: ToolSpec, params: dict[str, Any]) -> tuple[bool, str]:
    patterns = tuple(params.get("patterns", DEFAULT_CONFIRMATION_PATTERNS))
    matches = _any_param_matches(tool, patterns)
    if matches:
        return True, f"declares confirmation parameter(s): {sorted(matches)}"
    return False, (
        f"'{tool.name}' performs a destructive action but exposes no confirmation/"
        f"approval parameter (looked for {list(patterns)})"
    )


def _rule_forbidden_param(tool: ToolSpec, params: dict[str, Any]) -> tuple[bool, str]:
    patterns = tuple(params.get("patterns", ()))
    if not patterns:
        raise ValueError("forbidden_param rule requires a non-empty 'patterns' list")
    matches = _any_param_matches(tool, patterns)
    if matches:
        return False, (
            f"'{tool.name}' exposes forbidden parameter(s) {sorted(matches)} "
            f"(violates least privilege; patterns={list(patterns)})"
        )
    return True, f"exposes no forbidden parameters (patterns={list(patterns)})"


def _rule_description_required(tool: ToolSpec, params: dict[str, Any]) -> tuple[bool, str]:
    min_len = int(params.get("min_length", 1))
    desc = (tool.description or "").strip()
    if len(desc) >= min_len:
        return True, "has a description"
    return False, f"'{tool.name}' has no description (min_length={min_len})"


def _rule_params_documented(tool: ToolSpec, params: dict[str, Any]) -> tuple[bool, str]:
    undocumented = [
        name
        for name, schema in tool.params.items()
        if not str(schema.get("description", "")).strip()
    ]
    if undocumented:
        return False, f"undocumented parameter(s): {sorted(undocumented)}"
    return True, "all parameters documented"


RULES: dict[str, Callable[[ToolSpec, dict[str, Any]], tuple[bool, str]]] = {
    "confirmation_required": _rule_confirmation_required,
    "forbidden_param": _rule_forbidden_param,
    "description_required": _rule_description_required,
    "params_documented": _rule_params_documented,
}


@dataclass(frozen=True)
class Check:
    """One governance check loaded from a rubric."""

    id: str
    principle: str
    rule: str
    tool_glob: str
    control_refs: tuple[str, ...]
    severity: Severity
    params: dict[str, Any]

    def applies_to(self, tool: ToolSpec) -> bool:
        return _glob(tool.name, self.tool_glob)

    def evaluate(self, tool: ToolSpec) -> Finding:
        if not self.applies_to(tool):
            result, detail = CheckResult.NOT_APPLICABLE, "tool does not match applies_to"
        else:
            passed, detail = RULES[self.rule](tool, self.params)
            result = CheckResult.PASS if passed else CheckResult.FAIL
        return Finding(
            check_id=self.id,
            tool=tool.name,
            result=result,
            severity=self.severity,
            principle=self.principle,
            control_refs=self.control_refs,
            detail=detail,
        )


@dataclass(frozen=True)
class Rubric:
    """A named collection of checks."""

    name: str
    checks: tuple[Check, ...]

    def evaluate(self, tools: list[ToolSpec]) -> list[Finding]:
        """Cartesian evaluate every check against every tool.

        NOT_APPLICABLE findings are retained so coverage can be reported; the
        :class:`~mcp_govcheck.types.Scorecard` filters them out of pass-rate.
        """
        return [check.evaluate(tool) for tool in tools for check in self.checks]


def _parse_check(raw: dict[str, Any], default_severity: Severity) -> Check:
    missing = [k for k in ("id", "rule") if k not in raw]
    if missing:
        raise ValueError(f"check is missing required field(s) {missing}: {raw!r}")

    rule = raw["rule"]
    if rule not in RULES:
        raise ValueError(
            f"check {raw['id']!r} uses unknown rule {rule!r}. Known rules: {sorted(RULES)}"
        )

    control_refs = tuple(raw.get("control_refs", ()))
    unknown = controls.validate_refs(list(control_refs))
    if unknown:
        raise ValueError(
            f"check {raw['id']!r} references unknown control(s) {unknown}. "
            f"Add them to mcp_govcheck.controls or fix the rubric."
        )

    sev_raw = raw.get("severity")
    severity = Severity(sev_raw) if sev_raw else default_severity

    applies_to = raw.get("applies_to") or {}
    tool_glob = applies_to.get("tool", "*")

    return Check(
        id=raw["id"],
        principle=raw.get("principle", ""),
        rule=rule,
        tool_glob=tool_glob,
        control_refs=control_refs,
        severity=severity,
        params=raw.get("params", {}),
    )


def load_rubric(path: str | Path) -> Rubric:
    """Load and validate a rubric from a YAML file (fails loud on any error)."""
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return load_rubric_data(data, name=path.stem)


def load_rubric_data(data: dict[str, Any], name: str = "rubric") -> Rubric:
    """Load and validate a rubric from an already-parsed mapping."""
    default_severity = Severity(data.get("default_severity", "medium"))
    raw_checks = data.get("checks", [])
    if not raw_checks:
        raise ValueError("rubric contains no checks")

    seen: set[str] = set()
    checks: list[Check] = []
    for raw in raw_checks:
        check = _parse_check(raw, default_severity)
        if check.id in seen:
            raise ValueError(f"duplicate check id {check.id!r}")
        seen.add(check.id)
        checks.append(check)

    return Rubric(name=name, checks=tuple(checks))
