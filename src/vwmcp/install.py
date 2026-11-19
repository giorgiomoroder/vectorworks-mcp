"""Install the in-app bridge into a Vectorworks user Plug-ins folder."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from vwmcp import app, config

MENU_SCRIPT = "from vwmcp import vwmcp_bridge\nvwmcp_bridge.run_pending()\n"
HOME_FILE = "vwmcp_home.txt"  # read by the bridge: which folder's jobs to run


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


def install_plugin(target: Path, home: Path | str | None = None) -> str:
    """Copy the bridge into `target`. `home` (the server's VWMCP_HOME) is
    written to vwmcp_home.txt so this bridge runs that folder's jobs; without
    it the bridge uses ~/.vwmcp."""
    target.mkdir(parents=True, exist_ok=True)
    (target / "__init__.py").write_text(
        '"""vectorworks-mcp bridge package (see vwmcp_bridge.py)."""\n', encoding="utf-8"
    )
    (target / "vwmcp_bridge.py").write_text(app.bundled_bridge_source(), encoding="utf-8")
    home_file = target / HOME_FILE
    if home:
        home_file.write_text(str(home) + "\n", encoding="utf-8")
        where = f" (jobs from {home})"
    else:
        home_file.unlink(missing_ok=True)
        where = ""
    return (
        f"Installed vwmcp bridge {app.EXPECTED_BRIDGE_VERSION} to {target}{where}\n\n"
        "If you haven't yet, create the 'MCP Run Job' menu command once in Vectorworks "
        "(Tools > Plug-ins > Plug-in Manager > New > Command, Language: Python) with:\n\n"
        + MENU_SCRIPT
    )
