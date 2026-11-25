"""Shared MCP server instance and bridge access for tool modules."""

from __future__ import annotations

import contextvars
import functools
from importlib import resources
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from vwmcp import calls, config
from vwmcp.client import Bridge, BridgeError, WrongDocument
from vwmcp.journal import Journal

# The document the current tool call works in ({"name", "path"} or None).
# Set by require_document; vw() names it in every job so the bridge refuses
# to run in another document (the user may switch documents between two of
# our jobs). Each MCP request runs in its own task (and sync tools in a
# worker thread with a copy of that context), so the value never leaks into
# the next tool call.
DOCUMENT: contextvars.ContextVar[dict | None] = contextvars.ContextVar("vwmcp_document", default=None)

EXPECTED_BRIDGE_VERSION = "0.2.1"  # bridge 0.2: checked vs, document guard, libs by sha; 0.2.1: redraw after writes
# Vectorworks major versions this release was tested against (31 = 2026).
TESTED_VW_MAJORS = {31: "2026", 32: "2027"}  # 2027: 32.1.1, live 2026-11-19 (vs-notes)

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)

INSTRUCTIONS = f"""\
Tools for a live Vectorworks session (Spotlight-focused). This server talks
to "{config.DEFAULT_APP}" only; every call runs inside that app's open
document via the "MCP Run Job" menu command.

- Start a session with vw_list_documents (or vw_ping, which lists them too):
  several documents are often open and the user switches between them. Name
  the target on every write with document=; the write is refused if another
  document is active. Test writes belong on a throwaway document.
- Vectorworks merges back-to-back MCP edits into one Cmd-Z step, so to undo
  exactly one tool call use vw_revert_last (works for typed write tools).
- Objects are identified by UUID (stable across calls); never cache handles.
- Vectorworks embeds Python 3.9: code sent to vw_exec_python must be 3.9-
  compatible. Use vw_vs_lookup to find vs.* functions and signatures.
- Prefer typed tools (lighting devices, records, find) over raw Python.
- vw_screenshot shows the document window as an image without touching
  Vectorworks: use it to check drawn results, or to see a blocking dialog
  when other tools time out.
"""

mcp = MCPServer("vectorworks", instructions=INSTRUCTIONS)


@functools.cache
def get_bridge() -> Bridge:
    return Bridge()


@functools.cache
def get_journal() -> Journal:
    return Journal(get_bridge().root / "journal.jsonl")


def vw(fn: str, **kwargs):
    """Call a vwlib helper, mapping failures to MCP tool errors. Carries the
    request's document (require_document) so the bridge checks it first."""
    try:
        return calls.call(get_bridge(), fn, document=DOCUMENT.get(), **kwargs)
    except WrongDocument as e:
        want = (DOCUMENT.get() or {}).get("name", "")
        raise ToolError(f"Not done: {e} Bring {want!r} to the front (vw_switch_document) and "
                        "try again.") from e
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


BRIDGE_TABLES = ("vs_types.json", "vs_safety.json")  # installed beside the bridge


def bundled_data(name: str) -> str:
    """A data file shipped in the package (src/vwmcp/data/<name>)."""
    return resources.files("vwmcp").joinpath("data", name).read_text(encoding="utf-8")


DOCUMENT_HINT = ("document: name of the document this call is meant for (as vw_document_info / "
                 "vw_list_documents show it; \".vwx\" may be left out). If another document is "
                 "active, nothing is changed and the call fails; use vw_switch_document first.")


def _doc_key(name: str) -> str:
    name = (name or "").strip()
    if name.lower().endswith(".vwx"):
        name = name[:-4]
    return name.casefold()


def require_document(document: str | None) -> None:
    """Refuse a write when `document` is given and another document is active,
    and make every later call of this request name the document so the
    bridge checks again right before running each job."""
    DOCUMENT.set(None)
    if not document:
        return
    current = vw("current_document")
    if _doc_key(current) != _doc_key(document):
        raise ToolError(f"Not done: the active document is {current!r}, not {document!r}. "
                        "Bring the right one to the front (vw_switch_document) and try again.")
    DOCUMENT.set({"name": document})
