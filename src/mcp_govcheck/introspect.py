"""Turn an MCP server (or a static schema file) into ToolSpec objects.

This is the ONLY module that imports the `mcp` SDK, so the rest of the package
stays pure-Python and unit-testable without a live server. Two input paths:

* :func:`tools_from_schema` — parse a static JSON file (a list of tool
  descriptors, or an MCP ``tools/list`` response) into ToolSpec objects. No SDK.
* :func:`tools_from_server` — launch a stdio MCP server, call ``list_tools``,
  and convert the result. Imports the SDK lazily so importing this module never
  forces the dependency.

A tool's JSON-Schema ``inputSchema.properties`` maps directly to
:attr:`ToolSpec.params`.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

from .types import ToolSpec


class _ToolsPage(Protocol):
    """The shape of one `tools/list` page we depend on (SDK ``ListToolsResult``)."""

    tools: list[Any]
    nextCursor: str | None  # noqa: N815 — matches the MCP wire/SDK field name


def _params_from_input_schema(input_schema: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Extract ``{param_name: schema}`` from a JSON-Schema inputSchema."""
    if not input_schema:
        return {}
    props = input_schema.get("properties") or {}
    # Keep each property's schema dict verbatim (type, description, default, ...).
    return {name: dict(schema) for name, schema in props.items()}


def _toolspec_from_descriptor(d: dict[str, Any]) -> ToolSpec:
    """Build a ToolSpec from one tool descriptor (MCP shape or our own)."""
    name = d.get("name")
    if not name:
        raise ValueError(f"tool descriptor missing 'name': {d!r}")
    # Accept either MCP's "inputSchema" or a pre-extracted "params" mapping.
    if "params" in d:
        params = {k: dict(v) for k, v in d["params"].items()}
    else:
        params = _params_from_input_schema(d.get("inputSchema") or d.get("input_schema"))
    return ToolSpec(name=name, description=(d.get("description") or "").strip(), params=params)


def tools_from_descriptors(descriptors: list[dict[str, Any]]) -> list[ToolSpec]:
    return [_toolspec_from_descriptor(d) for d in descriptors]


def tools_from_schema(path: str | Path) -> list[ToolSpec]:
    """Load tools from a static JSON file.

    Accepts either a bare list of descriptors, or an object with a ``tools``
    key (the shape of an MCP ``tools/list`` result).
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("tools", [])
    if not isinstance(data, list):
        raise ValueError("schema file must be a list of tools or an object with a 'tools' list")
    return tools_from_descriptors(data)


def tools_from_server(command: str, args: list[str] | None = None) -> list[ToolSpec]:
    """Launch a stdio MCP server and introspect its tools.

    `command` is the executable (e.g. "python") and `args` its arguments
    (e.g. ["examples/asset_store_server.py"]). Runs the async MCP client
    handshake to completion and returns the discovered ToolSpecs.
    """
    import anyio  # lazy: only needed when actually talking to a server

    return anyio.run(_async_tools_from_server, command, args or [])


def _toolspec_from_mcp_tool(tool: Any) -> ToolSpec:
    """Convert one SDK ``Tool`` object into a ToolSpec."""
    return ToolSpec(
        name=tool.name,
        description=(getattr(tool, "description", "") or "").strip(),
        params=_params_from_input_schema(getattr(tool, "inputSchema", None)),
    )


async def _collect_tools(
    fetch_page: Callable[[str | None], Awaitable[_ToolsPage]],
) -> list[ToolSpec]:
    """Follow ``tools/list`` pagination to completion.

    ``fetch_page(cursor)`` fetches one page (``.tools`` + ``.nextCursor``). We
    keep fetching until ``nextCursor`` is falsy so tools beyond the first page
    are never silently dropped — a partial scan would look misleadingly clean.
    """
    specs: list[ToolSpec] = []
    cursor: str | None = None
    while True:
        page = await fetch_page(cursor)
        specs.extend(_toolspec_from_mcp_tool(tool) for tool in page.tools)
        cursor = page.nextCursor
        if not cursor:
            return specs


async def _async_tools_from_server(command: str, args: list[str]) -> list[ToolSpec]:
    # Imported lazily so the SDK is only required for live introspection.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=command, args=args)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        return await _collect_tools(lambda cursor: session.list_tools(cursor=cursor))
