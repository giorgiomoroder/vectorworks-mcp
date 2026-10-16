"""Shared MCP server instance and bridge access for tool modules."""

from __future__ import annotations

import functools
from importlib import resources
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from vwmcp import calls
from vwmcp.client import Bridge, BridgeError
from vwmcp.journal import Journal

EXPECTED_BRIDGE_VERSION = "0.1.0"

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)

INSTRUCTIONS = """\
Tools for a live Vectorworks session (Spotlight-focused). Every call runs
inside the user's open document via the "MCP Run Job" menu command.

- Vectorworks merges back-to-back MCP edits into one Cmd-Z step, so to undo
  exactly one tool call use vw_revert_last (works for typed write tools).
- Objects are identified by UUID (stable across calls); never cache handles.
- Vectorworks embeds Python 3.9: code sent to vw_exec_python must be 3.9-
  compatible. Use vw_vs_lookup to find vs.* functions and signatures.
- Prefer typed tools (lighting devices, records, find) over raw Python.
"""

mcp = MCPServer("vectorworks", instructions=INSTRUCTIONS)


@functools.cache
def get_bridge() -> Bridge:
    return Bridge()


@functools.cache
def get_journal() -> Journal:
    return Journal(get_bridge().root / "journal.jsonl")


def vw(fn: str, **kwargs):
    """Call a vwlib helper, mapping failures to MCP tool errors."""
    try:
        return calls.call(get_bridge(), fn, **kwargs)
    except calls.VWError as e:
        raise ToolError(f"{e}\n\n{e.traceback}".strip()) from e
    except BridgeError as e:
        raise ToolError(str(e)) from e


def bundled_bridge_source() -> str:
    """The in-app bridge shipped with this server (wheel or source checkout)."""
    packaged = resources.files("vwmcp").joinpath("_plugin", "vwmcp_bridge.py")
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    repo = Path(__file__).resolve().parents[2] / "vw-plugin" / "vwmcp" / "vwmcp_bridge.py"
    return repo.read_text(encoding="utf-8")
