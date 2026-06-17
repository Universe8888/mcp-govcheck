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


def test_missing_subcommand_errors():
    with pytest.raises(SystemExit):
        cli.main([])
