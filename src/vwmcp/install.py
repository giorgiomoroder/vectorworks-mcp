"""Install the in-app bridge into a Vectorworks user Plug-ins folder."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from vwmcp import app, config

MENU_SCRIPT = "from vwmcp import vwmcp_bridge\nvwmcp_bridge.run_pending()\n"
MENU_SCRIPT_LISTEN = "from vwmcp import vwmcp_bridge\nvwmcp_bridge.listen()\n"
LISTEN_STEP = (
    "Windows has no automatic trigger: create a second menu command 'MCP Listen' once "
    "(Tools > Plug-ins > Plug-in Manager > New > Command, Language: Python) with:\n\n"
    + MENU_SCRIPT_LISTEN
    + "\nAdd it to a menu like 'MCP Run Job'. While its window is open, Claude's requests run "
    "on their own; click Stop to edit the drawing yourself."
)
HOME_FILE = "vwmcp_home.txt"  # read by the bridge: which folder's jobs to run
MENU_COMMAND_FILE = "MCP Run Job.vsm"
MENU_STEP = (
    "If 'MCP Run Job' is not in a menu yet: Tools > Workspaces > Edit Current Workspace > "
    "Menus, drag it (under Miscellaneous) into Tools, OK. If it is missing from that list, "
    "restart Vectorworks once."
)


def bundled_menu_command() -> Path | None:
    """The prebuilt 'MCP Run Job' menu command (.vsm) shipped in the package
    (src/vwmcp/menu/). Vectorworks can't make .vsm files from text, but a
    copy works in any user Plug-ins folder."""
    path = Path(__file__).resolve().parent / "menu" / MENU_COMMAND_FILE
    return path if path.is_file() else None


def plugin_dir(
    vw_version: str = config.VW_VERSION,
    platform: str = sys.platform,
    home: Path | None = None,
    appdata: Path | None = None,
) -> Path:
    if platform == "darwin":
        home = home or Path.home()
        base = home / "Library/Application Support/Vectorworks"
    elif platform == "win32":
        appdata = appdata or Path(os.environ["APPDATA"])
        base = appdata / "Nemetschek/Vectorworks"
    else:
        raise SystemExit(f"Vectorworks does not run on {platform}")
    return base / vw_version / "Plug-ins" / "vwmcp"


def install_plugin(
    target: Path,
    home: Path | str | None = None,
    menu_command: Path | None = None,
    platform: str = sys.platform,
) -> str:
    """Copy the bridge into `target` and the 'MCP Run Job' command file next
    to it (into the Plug-ins folder) unless one is already there. `home` (the
    server's VWMCP_HOME) is written to vwmcp_home.txt so this bridge runs
    that folder's jobs; without it the bridge uses ~/.vwmcp."""
    target.mkdir(parents=True, exist_ok=True)
    (target / "__init__.py").write_text(
        '"""vectorworks-mcp bridge package (see vwmcp_bridge.py)."""\n', encoding="utf-8"
    )
    (target / "vwmcp_bridge.py").write_text(app.bundled_bridge_source(), encoding="utf-8")
    for name in app.BRIDGE_TABLES:  # the vs.* type and safety tables the bridge checks against
        (target / name).write_text(app.bundled_data(name), encoding="utf-8")
    home_file = target / HOME_FILE
    if home:
        home_file.write_text(str(home) + "\n", encoding="utf-8")
        where = f" (jobs from {home})"
    else:
        home_file.unlink(missing_ok=True)
        where = ""
    msg = (f"Installed vwmcp bridge {app.EXPECTED_BRIDGE_VERSION} with the vs.* type and safety "
           f"tables to {target}{where}\n")
    vsm = menu_command if menu_command is not None else bundled_menu_command()
    dest = target.parent / MENU_COMMAND_FILE
    if dest.exists():
        msg += f"Menu command already present: {dest}\n"
    elif vsm is not None:
        dest.write_bytes(Path(vsm).read_bytes())
        msg += f"Installed the 'MCP Run Job' menu command: {dest}\n"
    else:
        msg += (
            "No menu command file bundled: create 'MCP Run Job' once in Vectorworks "
            "(Tools > Plug-ins > Plug-in Manager > New > Command, Language: Python) with:\n\n"
            + MENU_SCRIPT
        )
    msg += "\n" + MENU_STEP + "\n"
    if platform == "win32":
        msg += "\n" + LISTEN_STEP + "\n"
    return msg
