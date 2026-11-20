"""Call vwlib helpers inside Vectorworks through the bridge."""

from __future__ import annotations

import json
from importlib import resources

from vwmcp.client import Bridge

VWLIB_SOURCE = resources.files("vwmcp").joinpath("vwlib.py").read_text(encoding="utf-8")


class VWError(RuntimeError):
    """Python raised inside Vectorworks."""

    def __init__(self, message: str, traceback: str = "", stdout: str = ""):
        super().__init__(message)
        self.traceback = traceback or ""
        self.stdout = stdout or ""


def raise_for_result(res: dict) -> dict:
    if not res.get("ok"):
        raise VWError(res.get("error") or "unknown error", res.get("traceback"), res.get("stdout"))
    return res


def call_result(bridge: Bridge, fn: str, timeout: float | None = None,
                document: dict | None = None, allow_dialogs: bool = False, **kwargs) -> dict:
    """Run vwlib.<fn>(**kwargs) in Vectorworks; return the full bridge result
    (value, stdout, ...). Raises VWError if the helper itself raised.

    vwlib travels inline until the bridge's version is known, then by
    reference (the bridge compiles it once per Vectorworks session).
    `document` and `allow_dialogs` are job options, never vwlib arguments."""
    # json.dumps -> repr gives a Python string literal, safe for any content.
    tail = f"import json as _json\nresult = {fn}(**_json.loads({json.dumps(kwargs)!r}))\n"
    opts = {"timeout": timeout, "document": document, "allow_dialogs": allow_dialogs}
    if bridge.supports_libs():
        res = bridge.run(tail, libs=[bridge.lib_ref("vwlib", VWLIB_SOURCE)], **opts)
    else:
        res = bridge.run(f"{VWLIB_SOURCE}\n{tail}", **opts)
    return raise_for_result(res)


def call(bridge: Bridge, fn: str, document: dict | None = None, **kwargs):
    """Run vwlib.<fn>(**kwargs) in Vectorworks and return its value."""
    return call_result(bridge, fn, document=document, **kwargs)["value"]
