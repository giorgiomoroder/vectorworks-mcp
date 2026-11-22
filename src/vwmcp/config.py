"""Which Vectorworks this server instance talks to, and which tools it offers.

One server process serves one Vectorworks version. To use two versions side by
side (say 2026 and 2027), register two servers with different environments:

    VWMCP_VW_VERSION=2027  VWMCP_HOME=~/.vwmcp-2027

and install the bridge into that version's Plug-ins folder with the same home
(`vwmcp install-plugin --vw-version 2027 --home ~/.vwmcp-2027`), so jobs,
results, the journal and the log never mix between the two apps.

Without VWMCP_VW_VERSION the year comes from VWMCP_APP ("Vectorworks 2027",
the older way to point at another app), else from the single Vectorworks
installed in /Applications, else 2026. With several versions installed and
nothing set, 2026 is assumed and `vwmcp doctor` says so.

VWMCP_TOOLS_OFF="spotlight,stage" hides tool groups (see TOOL_GROUPS) for
users who don't need them, e.g. architecture offices.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

FALLBACK_VERSION = "2026"


def installed_versions(apps: Path = Path("/Applications")) -> list[str]:
    """Years of the Vectorworks versions installed on this Mac, oldest first."""
    years = []
    if apps.is_dir():
        for d in apps.iterdir():
            m = re.fullmatch(r"Vectorworks (20\d\d)", d.name)
            if m and (d / f"{d.name}.app").exists():
                years.append(m.group(1))
    return sorted(years)


def _version_from_app(app: str) -> str | None:
    m = re.search(r"20\d\d", app)
    return m.group(0) if m else None


def detect_version(environ=os.environ, apps: Path = Path("/Applications")) -> str:
    env = environ.get("VWMCP_VW_VERSION")
    if env:
        return env
    from_app = _version_from_app(environ.get("VWMCP_APP", ""))
    if from_app:
        return from_app
    found = installed_versions(apps)
    if len(found) == 1:
        return found[0]
    return FALLBACK_VERSION


VW_VERSION = detect_version()
DEFAULT_APP = os.environ.get("VWMCP_APP", f"Vectorworks {VW_VERSION}")

# Tool groups that can be switched off with VWMCP_TOOLS_OFF (comma-separated).
TOOL_GROUPS = {
    "spotlight": [
        "vw_list_lighting_devices", "vw_set_lighting_device_fields", "vw_list_positions",
        "vw_lighting_device_report", "vw_insert_lighting_devices", "vw_mvr_check",
        "vw_import_hookup", "vw_lightwright_snapshot", "vw_lightwright_patch",
    ],
    "stage": [
        "vw_insert_truss_run", "vw_list_truss", "vw_insert_hoists", "vw_list_hoists",
        "vw_insert_stage_decks", "vw_insert_stage_steps",
        "vw_insert_stage_ramp", "vw_insert_soft_goods", "vw_insert_platform", "vw_insert_band",
    ],
    "plan": [
        "vw_export_geometry", "vw_render_layers", "vw_duplicate_layer", "vw_set_vertices",
    ],
    "drawing": ["vw_apply_class_standard", "vw_create_sheet"],
}


def tools_off(environ=os.environ) -> list[str]:
    """Tool names hidden by VWMCP_TOOLS_OFF; unknown group names are ignored."""
    names: list[str] = []
    for group in environ.get("VWMCP_TOOLS_OFF", "").split(","):
        names.extend(TOOL_GROUPS.get(group.strip().lower(), []))
    return names
