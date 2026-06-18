"""mcp-govcheck — design-time governance scorecard and control-mapped
compliance evidence for MCP servers.

Two entry points:

* :func:`scan` — introspect an MCP server (or static schema) and score its
  tool design against a governance rubric → :class:`~mcp_govcheck.types.Scorecard`.
* :func:`attest` — turn a tool-call log into control-mapped compliance evidence
  → :class:`~mcp_govcheck.types.EvidencePack`.

This is NOT a runtime gateway or firewall: it never sits in the request path.
It evaluates the *design* of an agent's tool surface and the *record* of its
tool use, the way an auditor would.
"""

from __future__ import annotations

from pathlib import Path

from . import controls, evidence, introspect, report, score
from .evidence import DEFAULT_POLICIES, EvidencePolicy, load_calls
from .evidence import attest as _attest_calls
from .rubric import Rubric, load_rubric, load_rubric_data
from .score import build_scorecard
from .types import EvidencePack, Scorecard, ToolSpec

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "scan",
    "attest",
    "scan_tools",
    "load_rubric",
    "load_rubric_data",
    "Rubric",
    "Scorecard",
    "EvidencePack",
    "ToolSpec",
    "EvidencePolicy",
    "DEFAULT_POLICIES",
    "controls",
    "report",
    "score",
    "introspect",
    "evidence",
]


def scan_tools(tools: list[ToolSpec], rubric: Rubric, target: str = "tools") -> Scorecard:
    """Score an already-introspected list of tools against a rubric."""
    findings = rubric.evaluate(tools)
    return build_scorecard(target=target, findings=findings, tools_scanned=len(tools))


def scan(
    source: str | Path,
    rubric: Rubric,
    *,
    command: str | None = None,
    args: list[str] | None = None,
) -> Scorecard:
    """Introspect a source and score it.

    * If `command` is given, launch that stdio MCP server (``source`` is a label).
    * Otherwise treat `source` as a path to a static tool-schema JSON file.
    """
    target = str(source)
    if command is not None:
        tools = introspect.tools_from_server(command, args or [])
    else:
        tools = introspect.tools_from_schema(source)
    return scan_tools(tools, rubric, target=target)


def attest(
    log_path: str | Path, policies: list[EvidencePolicy] | None = None
) -> EvidencePack:
    """Load a JSONL tool-call log and build a control-mapped evidence pack."""
    calls = load_calls(log_path)
    return _attest_calls(str(log_path), calls, policies or DEFAULT_POLICIES)
