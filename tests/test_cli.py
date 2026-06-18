"""Tests for the CLI: exit-code contract + scan/attest against bundled examples."""

import json
from pathlib import Path

import pytest

from mcp_govcheck import cli

REPO = Path(__file__).resolve().parent.parent
SAMPLE_LOG = REPO / "examples" / "sample_calls.jsonl"


def _write_schema(tmp_path, tools):
    p = tmp_path / "schema.json"
    p.write_text(json.dumps(tools), encoding="utf-8")
    return str(p)


def test_scan_clean_schema_exits_zero(tmp_path, capsys):
    # one fully-compliant read-only tool
    schema = _write_schema(tmp_path, [
        {"name": "get_asset", "description": "Read an asset by id.",
         "inputSchema": {"properties": {"asset_id": {"type": "integer", "description": "id"}}}}
    ])
    code = cli.main(["scan", schema])
    assert code == cli.EXIT_CLEAN
    assert "scorecard" in capsys.readouterr().out.lower()


def test_scan_violating_schema_exits_one(tmp_path, capsys):
    schema = _write_schema(tmp_path, [
        {"name": "delete_asset", "description": "Delete an asset permanently.",
         "inputSchema": {"properties": {"asset_id": {"type": "integer", "description": "id"}}}}
    ])
    code = cli.main(["scan", schema])
    assert code == cli.EXIT_FINDINGS  # destructive without confirmation


def test_scan_json_output_is_valid(tmp_path):
    schema = _write_schema(tmp_path, [
        {"name": "delete_asset", "description": "Delete an asset permanently.",
         "inputSchema": {"properties": {"asset_id": {"type": "integer", "description": "id"}}}}
    ])
    out = tmp_path / "sc.json"
    code = cli.main(["scan", schema, "--json", "--out", str(out)])
    assert code == cli.EXIT_FINDINGS
    data = json.loads(out.read_text())
    assert data["summary"]["failed"] >= 1


def test_attest_sample_log_exits_one(capsys):
    # sample log contains an unconfirmed delete -> a violated control
    code = cli.main(["attest", str(SAMPLE_LOG)])
    assert code == cli.EXIT_FINDINGS
    assert "evidence" in capsys.readouterr().out.lower()


def test_bad_schema_path_exits_two(capsys):
    code = cli.main(["scan", "does_not_exist.json"])
    assert code == cli.EXIT_ERROR
    assert "error" in capsys.readouterr().err.lower()


def test_empty_server_command_exits_two():
    assert cli.main(["scan", "--server", "   "]) == cli.EXIT_ERROR


def test_unwritable_out_path_exits_two(tmp_path, capsys):
    # --out points at an existing directory: write_text raises an OSError
    # (PermissionError on Windows / IsADirectoryError on POSIX). Per the
    # contract an unwritable output target is a usage error (2), not an
    # uncaught traceback that Python would exit 1 on (== EXIT_FINDINGS).
    schema = _write_schema(tmp_path, [
        {"name": "get_asset", "description": "Read an asset by id.",
         "inputSchema": {"properties": {"asset_id": {"type": "integer", "description": "id"}}}}
    ])
    code = cli.main(["scan", schema, "--out", str(tmp_path)])
    assert code == cli.EXIT_ERROR
    assert "error" in capsys.readouterr().err.lower()


def test_server_introspection_failure_exits_two(monkeypatch, capsys):
    # A missing optional SDK (ModuleNotFoundError) or a failed MCP handshake is
    # an environment/input error → EXIT_ERROR (2), never EXIT_FINDINGS (1).
    def boom(command, args):
        raise ModuleNotFoundError("No module named 'mcp'")

    monkeypatch.setattr(cli, "tools_from_server", boom)
    code = cli.main(["scan", "--server", "python whatever.py"])
    assert code == cli.EXIT_ERROR
    assert "error" in capsys.readouterr().err.lower()


def test_both_schema_and_server_exits_two(tmp_path, capsys):
    # Two mutually exclusive input modes: passing both must be rejected, not
    # silently resolved (which previously discarded the schema file).
    schema = _write_schema(tmp_path, [
        {"name": "get_asset", "description": "Read an asset by id.",
         "inputSchema": {"properties": {}}}
    ])
    code = cli.main(["scan", schema, "--server", "python server.py"])
    assert code == cli.EXIT_ERROR
    assert "both" in capsys.readouterr().err.lower()


def test_missing_subcommand_errors():
    with pytest.raises(SystemExit):
        cli.main([])
