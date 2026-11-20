"""`vwmcp doctor`: check the install without touching Vectorworks.

Everything here is file and process inspection. It never sends an Apple
Event or a job, so it is safe to run at any time, even while Vectorworks is
launching or showing a dialog. What it cannot check (the "MCP Run Job" menu
command and the macOS Automation permission) needs a live `vw_ping`.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vwmcp import app, config, install
from vwmcp.client import DEFAULT_ROOT

STALE_RESULT_AGE = 60 * 60  # results nobody collected (server timed out / died)
STALE_JOB_AGE = 10 * 60  # jobs far older than any server timeout


@dataclass
class Check:
    name: str
    ok: bool | None  # None = could not check here
    detail: str
    fix: str = ""

    @property
    def mark(self) -> str:
        return {True: "ok  ", False: "FAIL", None: "skip"}[self.ok]


def claude_desktop_config(home: Path, platform: str = sys.platform) -> Path:
    if platform == "win32":
        return Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "Claude/claude_desktop_config.json"
    return home / "Library/Application Support/Claude/claude_desktop_config.json"


def _configured_versions(home: Path, platform: str) -> set[str]:
    """VWMCP_VW_VERSION values set on server entries in the Claude configs."""
    out = set()
    for path in (claude_desktop_config(home, platform), home / ".claude.json"):
        try:
            servers = json.loads(path.read_text(encoding="utf-8")).get("mcpServers", {})
        except (OSError, ValueError):
            continue
        for entry in servers.values():
            v = ((entry or {}).get("env") or {}).get("VWMCP_VW_VERSION")
            if v:
                out.add(v)
    return out


def check_version_choice(
    vw_version: str, environ=os.environ, apps: Path = Path("/Applications"), configured: set[str] = frozenset()
) -> Check:
    """With several Vectorworks versions installed, the version must be explicit:
    in this process' env or on a server entry in the Claude configs."""
    found = config.installed_versions(apps)
    explicit = environ.get("VWMCP_VW_VERSION") or environ.get("VWMCP_APP") or vw_version in configured
    if len(found) > 1 and not explicit:
        return Check(
            "version", False,
            f"Vectorworks {', '.join(found)} are installed and nothing says which one this server is for "
            f"(assuming {vw_version})",
            "set VWMCP_VW_VERSION in the server's env (the installer does: VW_VERSION=2027 bash install-macos.sh)",
        )
    if vw_version not in found and found:
        return Check("version", None, f"Vectorworks {vw_version} is not in /Applications (installed: {', '.join(found)})")
    return Check("version", True, f"Vectorworks {vw_version}" + (" (only version installed)" if len(found) == 1 else ""))


def check_bridge(home: Path, vw_version: str, platform: str, root: Path | None = None) -> Check:
    try:
        appdata = Path(os.environ.get("APPDATA", home / "AppData/Roaming"))
        folder = install.plugin_dir(vw_version, platform=platform, home=home, appdata=appdata)
    except SystemExit as e:
        return Check("bridge", None, str(e))
    bridge = folder / "vwmcp_bridge.py"
    fix = "Run the installer again, or: vwmcp install-plugin"
    if not bridge.exists():
        return Check("bridge", False, f"not installed at {folder}", fix)
    m = re.search(r'^BRIDGE_VERSION\s*=\s*"([^"]+)"', bridge.read_text(encoding="utf-8"), re.M)
    found = m.group(1) if m else "unknown"
    if found != app.EXPECTED_BRIDGE_VERSION:
        return Check("bridge", False, f"{found} installed, server expects {app.EXPECTED_BRIDGE_VERSION}", fix)
    for name in app.BRIDGE_TABLES:
        table = folder / name
        if not table.exists():
            return Check("bridge", False, f"{found} at {folder}, but {name} (vs.* check table) is missing", fix)
        if table.read_text(encoding="utf-8") != app.bundled_data(name):
            return Check("bridge", False, f"{found} at {folder}, but {name} is outdated", fix)
    home_file = folder / install.HOME_FILE
    serves = Path(home_file.read_text(encoding="utf-8").strip()).expanduser() if home_file.exists() else None
    if root is not None:
        expected = Path(root).expanduser()
        bridge_root = serves if serves is not None else home / ".vwmcp"
        if bridge_root != expected:
            return Check(
                "bridge", False,
                f"{found} at {folder} runs jobs from {bridge_root}, but this server uses {expected}",
                f"vwmcp install-plugin --vw-version {vw_version} --home {expected}",
            )
    menu = folder.parent / install.MENU_COMMAND_FILE
    if not menu.exists():
        return Check(
            "bridge", False, f"{found} at {folder}, but no '{install.MENU_COMMAND_FILE}' in {folder.parent}",
            f"vwmcp install-plugin --vw-version {vw_version}" + (f" --home {serves}" if serves else ""),
        )
    return Check("bridge", True, f"{found} at {folder}" + (f", jobs from {serves}" if serves else ""))


def find_server(servers: dict, vw_version: str) -> tuple[str, dict] | None:
    """The mcpServers entry for this Vectorworks version: one whose env sets
    VWMCP_VW_VERSION to it, else (for the default version) the entry named
    'vectorworks' without a version in its env."""
    for name, entry in servers.items():
        env = (entry or {}).get("env") or {}
        if env.get("VWMCP_VW_VERSION") == vw_version:
            return name, entry
    entry = servers.get("vectorworks")
    if entry and vw_version == "2026" and not (entry.get("env") or {}).get("VWMCP_VW_VERSION"):
        return "vectorworks", entry
    return None


def _server_entry(path: Path, vw_version: str) -> tuple[bool | None, str]:
    """(ok, detail) for the Claude config file's server entry for vw_version."""
    if not path.exists():
        return None, f"no config at {path}"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return False, f"cannot read {path}: {e}"
    found = find_server(cfg.get("mcpServers") or {}, vw_version)
    if not found:
        return False, f"no server for Vectorworks {vw_version} in {path}"
    name, entry = found
    command = entry.get("command", "")
    if command and not Path(command).is_absolute():
        return True, f"'{name}': command {command!r} (not an absolute path; Claude Desktop needs one)"
    if command and not Path(command).exists():
        return False, f"'{name}': command {command!r} does not exist"
    return True, f"'{name}': {command} {' '.join(entry.get('args', []))}".strip()


def check_claude_desktop(home: Path, platform: str, vw_version: str = config.VW_VERSION) -> Check:
    ok, detail = _server_entry(claude_desktop_config(home, platform), vw_version)
    return Check("claude_desktop", ok, detail, "" if ok else "Re-run the installer or see docs/claude-config.md")


def check_claude_code(home: Path, vw_version: str = config.VW_VERSION) -> Check:
    ok, detail = _server_entry(home / ".claude.json", vw_version)
    if ok is None:
        detail = "Claude Code not set up (no ~/.claude.json)"
    name = "vectorworks" if vw_version == "2026" else f"vectorworks-{vw_version}"
    return Check("claude_code", ok, detail, "" if ok else
                 f"VW_VERSION={vw_version} bash scripts/install-macos.sh, or: claude mcp add --scope user "
                 f"{name} -e VWMCP_VW_VERSION={vw_version} -- uvx --from git+https://github.com/giorgiomoroder/vectorworks-mcp vwmcp")


def check_vectorworks(uptime: float | None, app_name: str, platform: str) -> Check:
    if platform != "darwin":
        return Check("vectorworks", None, "process check only implemented on macOS")
    if uptime is None:
        return Check("vectorworks", False, f"{app_name} is not running", "Open Vectorworks with a document")
    if uptime < 30:
        return Check("vectorworks", False, f"{app_name} launched {uptime:.0f}s ago; requests wait until 30s", "Wait a moment")
    return Check("vectorworks", True, f"{app_name} running for {uptime / 60:.0f} min")


def _older_than(folder: Path, pattern: str, age: float, now: float) -> list[Path]:
    if not folder.exists():
        return []
    return [p for p in folder.glob(pattern) if now - p.stat().st_mtime > age]


def check_runtime(root: Path, now: float, fix: bool) -> Check:
    if not root.exists():
        return Check("runtime", True, f"{root} not created yet (first request creates it)")
    stale_results = _older_than(root / "results", "*.json", STALE_RESULT_AGE, now)
    stale_jobs = _older_than(root / "jobs", "*.json", STALE_JOB_AGE, now)
    stale_jobs += _older_than(root / "jobs", "*.tmp", STALE_JOB_AGE, now)
    # .cancelled: jobs the server gave up on before Vectorworks took them (never ran)
    cancelled = _older_than(root / "jobs", "*.cancelled", STALE_JOB_AGE, now)
    # lib/<sha>.py: helper libraries sent by reference; old ones belong to older servers
    libs = _older_than(root / "lib", "*.py", 7 * 86400, now)
    counts = (f"{len(stale_results)} stale results, {len(stale_jobs)} stale jobs, "
              f"{len(cancelled)} cancelled jobs, {len(libs)} stale libraries")
    if not stale_results and not stale_jobs and not cancelled and not libs:
        return Check("runtime", True, f"{root} clean")
    if fix:
        for p in stale_results + stale_jobs + cancelled + libs:
            p.unlink(missing_ok=True)
        return Check("runtime", True, f"removed {counts}")
    return Check("runtime", True, f"{counts} in {root} (harmless)", "vwmcp doctor --fix removes them")


def check_log(root: Path, now: float) -> Check:
    log = root / "vwmcp.log"
    if not log.exists():
        return Check("log", True, "no errors logged")
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    recent = [ln for ln in lines[-200:] if _log_age(ln, now) < 24 * 3600]
    if not recent:
        return Check("log", True, "no errors in the last 24 h")
    return Check("log", True, f"{len(recent)} errors in the last 24 h; last: {recent[-1]}")


def _log_age(line: str, now: float) -> float:
    try:
        stamp = time.mktime(time.strptime(line[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return float("inf")
    return now - stamp


def run_checks(
    home: Path | None = None,
    root: Path = DEFAULT_ROOT,
    vw_version: str = config.VW_VERSION,
    platform: str = sys.platform,
    app_name: str | None = None,
    uptime: Callable[[], float | None] | None = None,
    now: float | None = None,
    fix: bool = False,
    apps: Path = Path("/Applications"),
    environ=os.environ,
) -> list[Check]:
    home = home or Path.home()
    now = time.time() if now is None else now
    if app_name is None:
        from vwmcp.trigger import DEFAULT_APP

        app_name = DEFAULT_APP
    if uptime is None:
        if platform == "darwin":
            from vwmcp.trigger import mac_app_uptime

            uptime = lambda: mac_app_uptime(app_name)  # noqa: E731
        else:
            uptime = lambda: None  # noqa: E731
    return [
        check_version_choice(vw_version, environ, apps, _configured_versions(home, platform)),
        check_bridge(home, vw_version, platform, root),
        check_claude_desktop(home, platform, vw_version),
        check_claude_code(home, vw_version),
        check_vectorworks(uptime(), app_name, platform),
        check_runtime(Path(root), now, fix),
        check_log(Path(root), now),
    ]


def format_report(checks: list[Check]) -> str:
    lines = [f"vwmcp {app.EXPECTED_BRIDGE_VERSION} doctor"]
    for c in checks:
        lines.append(f"  {c.mark} {c.name:15} {c.detail}")
        if c.fix and c.ok is not True:
            lines.append(f"       fix: {c.fix}")
        elif c.fix:
            lines.append(f"       {c.fix}")
    lines.append(
        "Not checked here: whether 'MCP Run Job' is in a menu, and the macOS Automation "
        "permission. Ask Claude to ping Vectorworks to test those."
    )
    return "\n".join(lines)
