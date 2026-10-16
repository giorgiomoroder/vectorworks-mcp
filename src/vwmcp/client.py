"""Server side of the job-folder bridge.

The server writes <root>/jobs/<id>.json, fires a trigger that makes
Vectorworks run the "MCP Run Job" menu command (which calls
vwmcp_bridge.run_pending), then waits for <root>/results/<id>.json.
"""

from __future__ import annotations

import itertools
import json
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

DEFAULT_ROOT = Path(os.environ.get("VWMCP_HOME", Path.home() / ".vwmcp"))
DEFAULT_TIMEOUT = float(os.environ.get("VWMCP_TIMEOUT", "30"))


class BridgeError(RuntimeError):
    """The bridge could not deliver a job or its result."""


class BridgeTimeout(BridgeError):
    pass


class TriggerError(BridgeError):
    pass


class Bridge:
    def __init__(
        self,
        root: Path | str = DEFAULT_ROOT,
        trigger: Callable[[], None] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = 0.05,
    ):
        self.root = Path(root)
        self.jobs = self.root / "jobs"
        self.results = self.root / "results"
        self.log_path = self.root / "vwmcp.log"
        if trigger is None:
            from vwmcp.trigger import default_trigger

            trigger = default_trigger(self.root)
        self.trigger = trigger
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._lock = threading.Lock()  # one job in flight: one trigger, one undo step
        self._seq = itertools.count()

    def log(self, message: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().isoformat(timespec="seconds")
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {message}\n")

    def _new_job_id(self) -> str:
        # Zero-padded so the bridge's name sort is submission order.
        return f"{time.time_ns():020d}-{os.getpid()}-{next(self._seq):06d}"

    def run(self, code: str, timeout: float | None = None) -> dict:
        """Run code inside Vectorworks; return the bridge's result dict."""
        timeout = self.timeout if timeout is None else timeout
        with self._lock:
            return self._run_locked(code, timeout)

    def _run_locked(self, code: str, timeout: float) -> dict:
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.results.mkdir(parents=True, exist_ok=True)
        job_id = self._new_job_id()
        job_path = self.jobs / f"{job_id}.json"
        result_path = self.results / f"{job_id}.json"
        job = {"id": job_id, "code": code, "created": time.time(), "ttl": timeout}
        tmp = job_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(job), encoding="utf-8")
        os.replace(tmp, job_path)

        try:
            self.trigger()
        except TriggerError as e:
            self._withdraw(job_path)
            self.log(f"trigger failed for job {job_id}: {e}")
            raise

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if result_path.exists():
                return self._consume(result_path)
            time.sleep(self.poll_interval)

        if self._withdraw(job_path):
            msg = (
                f"Vectorworks did not pick up the job within {timeout:g}s. "
                "Check that a document is open, no dialog is showing, and the "
                "'MCP Run Job' menu command is in your workspace."
            )
        else:
            # Claimed but unfinished: still running inside Vectorworks.
            msg = (
                f"Job is still running in Vectorworks after {timeout:g}s; "
                f"its result will land in {result_path}."
            )
        self.log(f"timeout job {job_id}: {msg}")
        raise BridgeTimeout(msg)

    def _withdraw(self, job_path: Path) -> bool:
        """Remove a job Vectorworks has not claimed. True if it was unclaimed."""
        try:
            job_path.unlink()
            return True
        except FileNotFoundError:
            return False

    def _consume(self, result_path: Path) -> dict:
        res = json.loads(result_path.read_text(encoding="utf-8"))
        result_path.unlink()
        return res
