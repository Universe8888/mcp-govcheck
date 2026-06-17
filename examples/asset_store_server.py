"""Demo MCP server: an in-memory IT-asset store with DELIBERATELY MIXED governance.

This exists so `mcp-govcheck scan` has a real, runnable target that produces
real findings. Some tools are well-designed (documented params, confirmation on
destructive ops); others intentionally violate the default rubric so the
scorecard discriminates good design from bad.

Run standalone:        python examples/asset_store_server.py
Scan it:               mcp-govcheck scan --server "python examples/asset_store_server.py"

Parameter descriptions use Annotated[..., Field(description=...)] because that
is what propagates into the MCP inputSchema (plain docstring "Args:" does not).

Intentional violations (what scan should catch):
  * delete_asset  — destructive, NO confirmation parameter      -> FAIL high
  * purge_all     — destructive + wildcard 'scope' + 'force'     -> FAIL high + least-privilege
  * update_asset  — undocumented parameter 'note'                -> FAIL params_documented (low)
Compliant tools (should PASS every check):
  * get_asset     — read-only, all params documented
  * retire_asset  — destructive but exposes documented 'confirm' -> PASS
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("asset-store")

_ASSETS: dict[int, dict] = {1: {"id": 1, "tag": "LAP-001", "status": "active"}}


@mcp.tool()
def get_asset(
    asset_id: Annotated[int, Field(description="The numeric id of the asset to read.")],
) -> dict:
    """Return one asset by its id."""
    return _ASSETS.get(asset_id, {})


@mcp.tool()
def retire_asset(
    asset_id: Annotated[int, Field(description="The asset to retire.")],
    confirm: Annotated[bool, Field(description="Must be true to proceed (HITL gate).")] = False,
) -> str:
    """Retire an asset (reversible state change). Requires confirmation."""
    if not confirm:
        return "confirmation required"
    if asset_id in _ASSETS:
        _ASSETS[asset_id]["status"] = "retired"
    return "retired"


@mcp.tool()
def update_asset(
    asset_id: Annotated[int, Field(description="The asset to update.")],
    status: Annotated[str, Field(description="The new status value.")],
    note: str = "",
) -> str:
    """Update an asset's status."""
    # 'note' is intentionally undocumented (no Field) -> params_documented FAIL.
    if asset_id in _ASSETS:
        _ASSETS[asset_id]["status"] = status
    return "updated"


@mcp.tool()
def delete_asset(
    asset_id: Annotated[int, Field(description="The asset to delete.")],
) -> str:
    """Permanently delete an asset."""
    # Destructive with NO confirmation parameter -> confirmation_required FAIL.
    _ASSETS.pop(asset_id, None)
    return "deleted"


@mcp.tool()
def purge_all(
    scope: Annotated[str, Field(description="Which assets to purge.")] = "all",
    force: Annotated[bool, Field(description="Skip safety checks.")] = False,
) -> str:
    """Delete many assets at once."""
    # Destructive, wildcard scope + force escape hatch, no confirm -> multiple FAILs.
    _ASSETS.clear()
    return "purged"


if __name__ == "__main__":
    mcp.run()
