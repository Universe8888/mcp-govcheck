"""Tests for the static-schema introspection path (no live server / no SDK)."""

import json

import pytest

from mcp_govcheck import introspect
from mcp_govcheck.types import ToolSpec


def test_toolspec_from_mcp_input_schema():
    desc = {
        "name": "delete_asset",
        "description": "Delete an asset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "integer", "description": "id"},
                "confirm": {"type": "boolean"},
            },
        },
    }
    spec = introspect.tools_from_descriptors([desc])[0]
    assert isinstance(spec, ToolSpec)
    assert spec.name == "delete_asset"
    assert spec.param_names() == {"asset_id", "confirm"}
    assert spec.params["asset_id"]["description"] == "id"


def test_toolspec_from_preextracted_params():
    desc = {"name": "x", "params": {"a": {"type": "string", "description": "d"}}}
    spec = introspect.tools_from_descriptors([desc])[0]
    assert spec.params["a"]["type"] == "string"


def test_missing_name_raises():
    with pytest.raises(ValueError, match="missing 'name'"):
        introspect.tools_from_descriptors([{"description": "no name"}])


def test_tools_from_schema_bare_list(tmp_path):
    p = tmp_path / "schema.json"
    p.write_text(json.dumps([{"name": "get_asset", "inputSchema": {"properties": {}}}]))
    specs = introspect.tools_from_schema(p)
    assert [s.name for s in specs] == ["get_asset"]


def test_tools_from_schema_tools_list_wrapper(tmp_path):
    p = tmp_path / "schema.json"
    p.write_text(json.dumps({"tools": [{"name": "a", "inputSchema": {"properties": {}}}]}))
    assert introspect.tools_from_schema(p)[0].name == "a"


def test_tools_from_schema_rejects_garbage(tmp_path):
    p = tmp_path / "schema.json"
    p.write_text(json.dumps(42))
    with pytest.raises(ValueError, match="must be a list of tools"):
        introspect.tools_from_schema(p)


def test_empty_input_schema_yields_no_params():
    spec = introspect.tools_from_descriptors([{"name": "x"}])[0]
    assert spec.params == {}


class _Tool:
    def __init__(self, name):
        self.name = name
        self.description = ""
        self.inputSchema = {"properties": {}}


class _Page:
    def __init__(self, tools, next_cursor):
        self.tools = tools
        self.nextCursor = next_cursor


def test_collect_tools_follows_pagination_cursor():
    # MCP's tools/list is paginated: a page carries nextCursor and the caller
    # must keep fetching until it is None. Tools past the first page must not be
    # dropped (a governance scan that silently skips tools is worse than useless).
    import anyio

    pages = {
        None: _Page([_Tool("a"), _Tool("b")], "cur1"),
        "cur1": _Page([_Tool("c")], "cur2"),
        "cur2": _Page([_Tool("d")], None),
    }
    seen_cursors = []

    async def fetch(cursor):
        seen_cursors.append(cursor)
        return pages[cursor]

    specs = anyio.run(introspect._collect_tools, fetch)
    assert [s.name for s in specs] == ["a", "b", "c", "d"]
    assert seen_cursors == [None, "cur1", "cur2"]


def test_collect_tools_single_page():
    import anyio

    page = _Page([_Tool("only")], None)

    async def fetch(cursor):
        return page

    specs = anyio.run(introspect._collect_tools, fetch)
    assert [s.name for s in specs] == ["only"]
