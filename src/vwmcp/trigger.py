"""Ways to make Vectorworks run the "MCP Run Job" menu command.

macOS: AppleScript `run VectorScript` calling DoMenuTextByName. The menu
command gives the job a real document/undo context. Sending Python
directly (`run Python script`) is NOT used: in Vectorworks 2026 any
document write from that context, or any script sent while the app is
launching, crashes Vectorworks.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from vwmcp.client import TriggerError

from vwmcp.config import DEFAULT_APP  # noqa: F401  (re-exported for tools)

MENU_COMMAND = "MCP Run Job"
MIN_UPTIME = float(os.environ.get("VWMCP_MIN_UPTIME", "30"))


def _titles_visible() -> bool | None:
    """Screen Recording permission (window titles readable); None if unknown."""
    try:
        from vwmcp import screenshot
        return screenshot.screen_capture_allowed()
    except Exception:  # noqa: BLE001
        return None


def _mac_windows(app: str) -> list:
    """Vectorworks' on-screen windows (CoreGraphics, no Apple Event); [] when
    that fails, which only disables the start-screen preflight."""
    try:
        from vwmcp import screenshot

        return screenshot.mac_windows(app)
    except Exception:  # noqa: BLE001 - the preflight never blocks on its own failure
        return []


def parse_etime(text: str) -> int:
    """Parse ps etime ([[dd-]hh:]mm:ss) into seconds."""
    days, _, rest = text.strip().rpartition("-")
    parts = [int(p) for p in rest.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return (int(days) if days else 0) * 86400 + h * 3600 + m * 60 + s


def mac_app_uptime(app: str) -> float | None:
    """Seconds since the Vectorworks process started, or None if not running."""
    pattern = f"/{app}.app/Contents/MacOS/Vectorworks$"
    found = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    pids = found.stdout.split()
    if not pids:
        return None
    ps = subprocess.run(["ps", "-o", "etime=", "-p", pids[0]], capture_output=True, text=True)
    return parse_etime(ps.stdout) if ps.stdout.strip() else None


class MacTrigger:
    def __init__(
        self,
        root: Path,
        app: str = DEFAULT_APP,
        min_uptime: float = MIN_UPTIME,
        uptime: Callable[[], float | None] | None = None,
        spawn: Callable[[list[str]], subprocess.Popen] | None = None,
        busy_grace: float = 10.0,
        poll_interval: float = 0.05,
        windows: Callable[[], list] | None = None,
    ):
        self.root = Path(root)
        self.app = app
        self.min_uptime = min_uptime
        self.uptime = uptime or (lambda: mac_app_uptime(app))
        self.windows = windows or (lambda: _mac_windows(app))
        self.titles_visible = _titles_visible
        self.spawn = spawn or (
            lambda args: subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        )
        self.busy_grace = busy_grace
        self.poll_interval = poll_interval
        self._pending: subprocess.Popen | None = None

    def in_flight(self) -> bool:
        """An osascript we started has not returned yet (the client then
        does not re-fire the trigger while a job waits to be claimed)."""
        return self._pending is not None and self._pending.poll() is None

    def target_alive(self) -> bool:
        """Vectorworks is still running (asked while a claimed job runs)."""
        return self.uptime() is not None

    def _previous_still_running(self) -> bool:
        # osascript can return a moment after the result file lands (e.g. while
        # Vectorworks redraws), so allow a grace period before calling it stuck.
        if self._pending is None:
            return False
        deadline = time.monotonic() + self.busy_grace
        while self._pending.poll() is None:
            if time.monotonic() >= deadline:
                return True
            time.sleep(self.poll_interval)
        return False

    def __call__(self) -> None:
        up = self.uptime()
        if up is None:
            raise TriggerError(f"{self.app} is not running. Open it with a document first.")
        if up < self.min_uptime:
            raise TriggerError(
                f"{self.app} is still starting ({up:.0f}s). Try again in a few seconds."
            )
        from vwmcp.screenshot import has_document_window

        if has_document_window(self.windows(), self.app, self.titles_visible()) is False:
            raise TriggerError(
                f"No document is open in {self.app} (only the start screen). A job sent now "
                "would crash Vectorworks. Open a document first."
            )
        if self._previous_still_running():
            raise TriggerError(
                f"{self.app} has not answered the previous request; a dialog is "
                "probably open. Close it in Vectorworks and retry."
            )
        vss = self.root / "trigger.vss"
        self.root.mkdir(parents=True, exist_ok=True)
        vss.write_text(
            f"PROCEDURE T; BEGIN DoMenuTextByName('{MENU_COMMAND}', 0); END; RUN(T);",
            encoding="utf-8",
        )
        script = f'tell application "{self.app}" to run VectorScript (read POSIX file "{vss}")'
        self._pending = self.spawn(["osascript", "-e", script])


def manual_trigger() -> None:
    """No automation available: the user runs MCP Run Job (or Listen) themselves."""


def default_trigger(root: Path) -> Callable[[], None]:
    if sys.platform == "darwin":
        return MacTrigger(root)
    return manual_trigger
