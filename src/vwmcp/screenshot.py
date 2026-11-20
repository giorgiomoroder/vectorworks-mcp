"""Capture the Vectorworks document window as an image (macOS).

Finds the window through CoreGraphics' window list (ctypes, stdlib only) and
grabs it with `screencapture -l <window id>`. This never touches Vectorworks
itself: no Apple Event, no job, so it also works while a dialog is blocking
the bridge, which makes it the way to *see* what is blocking.

Needs Screen Recording permission for the app that runs the server
(Claude Desktop, Terminal, ...). Without it the capture is black or fails.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from vwmcp.client import DEFAULT_ROOT

KEEP_CAPTURES = 10


class ScreenshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class Window:
    id: int
    title: str
    layer: int
    x: float
    y: float
    width: float
    height: float

    @property
    def area(self) -> float:
        return self.width * self.height

    def as_dict(self) -> dict:
        return asdict(self)


# CoreGraphics window levels that mean "something is in front of the document".
WINDOW_LEVELS = {3: "floating", 8: "modal dialog", 101: "popup/contextual menu"}


def blocking_windows(windows: list[Window]) -> list[dict]:
    """Non-document windows (dialogs, menus) that stop Vectorworks from running
    jobs, with a label for the level so the caller can say which it is."""
    out = []
    for w in windows:
        kind = normal_level_blocker(w) if w.layer == 0 else WINDOW_LEVELS.get(
            w.layer, "other (level %d)" % w.layer)
        if kind is None:
            continue
        d = w.as_dict()
        d["kind"] = kind
        out.append(d)
    return out


# Dialogs Vectorworks shows at the normal window level (live 2026-11-20):
# their title gives them away, not their level.
NORMAL_LEVEL_DIALOGS = {
    "Object Preferences": "dialog (Object Preferences of a plug-in: click OK or Cancel in Vectorworks)",
    "Script Errors": "dialog (Script Errors: click OK in Vectorworks)",
}


def normal_level_blocker(w: Window) -> str | None:
    """Label for a level-0 window that still blocks jobs, else None."""
    if is_script_error_alert(w):
        return "alert (Script error: click OK in Vectorworks)"
    return NORMAL_LEVEL_DIALOGS.get(w.title.strip())


def is_script_error_alert(w: Window) -> bool:
    """The "A Script error has occurred" alert (live 2026-11-20, VW 2026): a
    small window titled just "Vectorworks" at the normal window level, so the
    level alone does not reveal it. It blocks jobs until the user clicks OK."""
    return w.title.strip() == "Vectorworks" and w.height < 300 and w.width < 700


# Titles of Vectorworks' own windows when no document is open (the start
# screen) besides the app's name itself. Extend after the live check
# (vs-notes "Start screen").
START_SCREEN_TITLES = {"Vectorworks", "Home Screen", "Start Screen"}


def has_document_window(windows: list[Window], app: str) -> bool | None:
    """True if a document window is on screen, False if only the start screen
    (and dialogs or helper windows) are, None if we cannot tell: no titles at
    all (the Screen Recording permission hides them) or no windows.
    A job sent while only the start screen shows crashes Vectorworks 2026
    and 2027 (found by Keystone), so the trigger refuses on False."""
    normal = [w for w in windows if w.layer == 0 and w.height >= 200]
    titled = [w for w in normal if w.title.strip()]
    if not titled:
        return None
    start = START_SCREEN_TITLES | {app}
    return any(w.title.strip() not in start and normal_level_blocker(w) is None for w in titled)


def pick_window(windows: list[Window], title: str | None = None) -> Window:
    """The document window: normal layer, matching title if given, else the largest."""
    normal = [w for w in windows if w.layer == 0 and normal_level_blocker(w) is None]
    if title:
        needle = title.lower()
        normal = [w for w in normal if needle in w.title.lower()]
        if not normal:
            titles = ", ".join(repr(w.title) for w in windows if w.layer == 0) or "none"
            raise ScreenshotError(f"No Vectorworks window titled like {title!r}. Open: {titles}.")
    if not normal:
        raise ScreenshotError(
            "Vectorworks has no document window on screen. Open a drawing (and check "
            "the window isn't minimized)."
        )
    return max(normal, key=lambda w: w.area)


def mac_windows(owner_contains: str) -> list[Window]:
    """On-screen windows whose owning app name contains `owner_contains`."""
    if sys.platform != "darwin":
        raise ScreenshotError("Window capture is only implemented on macOS.")
    cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
    cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
    cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    cf.CFNumberGetValue.restype = ctypes.c_bool
    cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    utf8 = 0x08000100
    double_type = 13
    on_screen_only, exclude_desktop = 1 << 0, 1 << 4

    keys: dict[str, int] = {}

    def key(name: str) -> int:
        if name not in keys:
            keys[name] = cf.CFStringCreateWithCString(None, name.encode(), utf8)
        return keys[name]

    def string(d: int, name: str) -> str:
        v = cf.CFDictionaryGetValue(d, key(name))
        if not v:
            return ""
        buf = ctypes.create_string_buffer(2048)
        return buf.value.decode("utf-8", "replace") if cf.CFStringGetCString(v, buf, 2048, utf8) else ""

    def number(d: int, name: str) -> float:
        v = cf.CFDictionaryGetValue(d, key(name))
        out = ctypes.c_double()
        if v and cf.CFNumberGetValue(v, double_type, ctypes.byref(out)):
            return out.value
        return 0.0

    arr = cg.CGWindowListCopyWindowInfo(on_screen_only | exclude_desktop, 0)
    found: list[Window] = []
    try:
        for i in range(cf.CFArrayGetCount(arr)):
            d = cf.CFArrayGetValueAtIndex(arr, i)
            if owner_contains not in string(d, "kCGWindowOwnerName"):
                continue
            bounds = cf.CFDictionaryGetValue(d, key("kCGWindowBounds"))
            found.append(
                Window(
                    id=int(number(d, "kCGWindowNumber")),
                    title=string(d, "kCGWindowName"),
                    layer=int(number(d, "kCGWindowLayer")),
                    x=number(bounds, "X") if bounds else 0.0,
                    y=number(bounds, "Y") if bounds else 0.0,
                    width=number(bounds, "Width") if bounds else 0.0,
                    height=number(bounds, "Height") if bounds else 0.0,
                )
            )
    finally:
        cf.CFRelease(arr)
        for k in keys.values():
            cf.CFRelease(k)
    return found


Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def capture(window: Window, out: Path, max_width: int | None = 1600, run: Runner = _run) -> Path:
    """screencapture the window to `out` (PNG), shrinking it to max_width pixels."""
    out.parent.mkdir(parents=True, exist_ok=True)
    res = run(["screencapture", "-x", "-o", "-l", str(window.id), str(out)])
    if res.returncode != 0 or not out.exists():
        raise ScreenshotError(
            "screencapture failed. Give the app running this server (Claude, Terminal) "
            "Screen Recording permission in System Settings > Privacy & Security. "
            f"{(res.stderr or '').strip()}"
        )
    if max_width:
        run(["sips", "-Z", str(max_width), str(out)])
    return out


def prune(folder: Path, keep: int = KEEP_CAPTURES) -> None:
    files = sorted(folder.glob("*.png"))
    for old in files[:-keep] if keep else files:
        old.unlink(missing_ok=True)


def screenshot(
    app: str = "Vectorworks 2026",
    root: Path = DEFAULT_ROOT,
    title: str | None = None,
    max_width: int | None = 1600,
    windows: Callable[[str], list[Window]] = mac_windows,
    run: Runner = _run,
) -> tuple[Path, Window, list[dict]]:
    """Capture the document window. Also returns the other Vectorworks windows
    (dialogs, open menus) that would keep a job from running."""
    owner = app.split(" ")[0]  # "Vectorworks 2026" owns windows as "Vectorworks 2026"
    found = windows(owner)
    window = pick_window(found, title)
    folder = Path(root) / "screenshots"
    out = folder / time.strftime("%Y%m%d-%H%M%S.png")
    capture(window, out, max_width, run)
    prune(folder)
    return out, window, blocking_windows(found)
