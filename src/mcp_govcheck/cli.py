"""Command-line interface for mcp-govcheck.

    mcp-govcheck scan   <schema.json> [--rubric R] [--json] [--out F]
    mcp-govcheck scan   --server "python examples/asset_store_server.py" [...]
    mcp-govcheck attest <calls.jsonl>  [--json] [--out F]

Exit codes (stable contract — usable as a CI gate):
    0  clean        (scan: no failures · attest: no violations)
    1  findings     (scan: >=1 failure · attest: >=1 violated control)
    2  usage/input error
"""

from __future__ import annotations

import argparse
import contextlib
import shlex
import sys
from pathlib import Path

from . import attest as _attest
from . import report, scan_tools
from .introspect import tools_from_schema, tools_from_server
from .rubric import Rubric, load_rubric
from .types import ToolSpec

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

_DEFAULT_RUBRIC = Path(__file__).resolve().parent.parent.parent / "rubrics" / "default.yaml"


def _load_rubric(path: str | None) -> Rubric:
    rubric_path = Path(path) if path else _DEFAULT_RUBRIC
    if not rubric_path.exists():
        raise FileNotFoundError(f"rubric not found: {rubric_path}")
    return load_rubric(rubric_path)


def _emit(text: str, out: str | None) -> None:
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(text)


def _introspect_server(server: str) -> list[ToolSpec]:
    """Launch a stdio MCP server and introspect it, translating any failure
    (empty command, missing SDK, failed handshake) into a ``ValueError`` so the
    CLI surfaces it as a usage/input error (exit 2), never a governance finding.
    """
    parts = shlex.split(server)
    if not parts:
        raise ValueError("--server command is empty")
    try:
        return tools_from_server(parts[0], parts[1:])
    except (ValueError, OSError):
        raise  # already an input/environment error; let main() format it
    except Exception as exc:  # missing SDK, handshake/protocol error, anyio group
        raise ValueError(f"could not introspect server {server!r}: {exc}") from exc


def _cmd_scan(ns: argparse.Namespace) -> int:
    rubric = _load_rubric(ns.rubric)
    if ns.server:
        if ns.source:
            raise ValueError("pass either a schema file or --server, not both")
        tools = _introspect_server(ns.server)
        target = ns.server
    else:
        if not ns.source:
            raise ValueError("provide a schema file or --server")
        tools = tools_from_schema(ns.source)
        target = ns.source
    scorecard = scan_tools(tools, rubric, target=target)
    text = (
        report.scorecard_to_json(scorecard)
        if ns.json
        else report.scorecard_to_markdown(scorecard)
    )
    _emit(text, ns.out)
    return EXIT_FINDINGS if scorecard.failures else EXIT_CLEAN


def _cmd_attest(ns: argparse.Namespace) -> int:
    pack = _attest(ns.log)
    text = (
        report.evidence_to_json(pack) if ns.json else report.evidence_to_markdown(pack)
    )
    _emit(text, ns.out)
    return EXIT_FINDINGS if pack.violated else EXIT_CLEAN


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcp-govcheck",
        description="Design-time governance scorecard + control-mapped evidence for MCP servers.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sc = sub.add_parser("scan", help="score an MCP server's tool design against a rubric")
    sc.add_argument("source", nargs="?", help="path to a tool-schema JSON file")
    sc.add_argument("--server", help='launch a stdio MCP server, e.g. "python server.py"')
    sc.add_argument(
        "--rubric", help="path to a rubric YAML (default: bundled rubrics/default.yaml)"
    )
    sc.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    sc.add_argument("--out", help="write output to this file instead of stdout")
    sc.set_defaults(func=_cmd_scan)

    at = sub.add_parser("attest", help="build control-mapped evidence from a tool-call log")
    at.add_argument("log", help="path to a JSONL tool-call log")
    at.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    at.add_argument("--out", help="write output to this file instead of stdout")
    at.set_defaults(func=_cmd_attest)

    return p


def _force_utf8_stdio() -> None:
    """Ensure stdout/stderr can emit the report glyphs (e.g. ✅/❌) on Windows,
    where the default console codec (cp1252) raises UnicodeEncodeError."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            # Best-effort; never break the CLI if the stream can't be reconfigured.
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = build_parser()
    ns = parser.parse_args(argv)
    try:
        return int(ns.func(ns))
    except (OSError, ValueError) as exc:
        # OSError covers bad input paths and unwritable --out targets
        # (PermissionError / IsADirectoryError / NotADirectoryError);
        # ValueError covers malformed schemas/logs and rejected CLI usage.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
