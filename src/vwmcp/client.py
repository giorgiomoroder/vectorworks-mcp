"""Server side of the job-folder bridge.

The server writes <root>/jobs/<id>.json (via .tmp), fires the trigger that
makes Vectorworks run "MCP Run Job" (vwmcp_bridge.run_pending), then waits
in two phases:

1. up to `claim_timeout` (15 s) for Vectorworks to claim the job (the bridge
   renames it to .running). Not claimed in time: the server renames it to
   .cancelled. If that rename succeeds the job can never run (never_ran); if
   it fails, Vectorworks claimed it at that moment and the server keeps
   waiting. While unclaimed, the trigger is re-fired every 2 s (an Apple
   Event can be swallowed while Vectorworks is busy).
2. up to `timeout` for the result of a claimed job. Every 2 s the trigger's
   target_alive() is asked whether Vectorworks still runs, so a quit or
   crash is reported at once instead of after the timeout.

Helper libraries (vwlib) are written once to <root>/lib/<sha>.py and sent by
reference; the bridge compiles them once per Vectorworks session.
"""

from __future__ import annotations

import contextlib
import hashlib
import itertools
import json
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

DEFAULT_ROOT = Path(os.environ.get("VWMCP_HOME", Path.home() / ".vwmcp"))
# Result wait after Vectorworks took the job (long inserts are fine).
DEFAULT_TIMEOUT = float(os.environ.get("VWMCP_TIMEOUT", "120"))
# Wait for Vectorworks to take the job at all (a dialog or menu blocks it).
DEFAULT_CLAIM_TIMEOUT = float(os.environ.get("VWMCP_CLAIM_TIMEOUT", "15"))
STALE_AFTER = 3600.0  # leftovers older than this are removed by housekeep()
RETRIGGER_AFTER = 2.0
ALIVE_EVERY = 2.0


class BridgeError(RuntimeError):
    """The bridge could not deliver a job or its result."""

    never_ran = False  # True: the job never ran in Vectorworks, nothing changed


class BridgeTimeout(BridgeError):
    pass


class TriggerError(BridgeError):
    never_ran = True


class WrongDocument(BridgeError):
    """The bridge found another document active than the one the job named."""

    never_ran = True


def _version_tuple(v: str | None) -> tuple:
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return ()


class Bridge:
    def __init__(
        self,
        root: Path | str = DEFAULT_ROOT,
        trigger: Callable[[], None] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = 0.05,
        claim_timeout: float = DEFAULT_CLAIM_TIMEOUT,
    ):
        self.root = Path(root)
        self.jobs = self.root / "jobs"
        self.results = self.root / "results"
        self.libdir = self.root / "lib"
        self.log_path = self.root / "vwmcp.log"
        if trigger is None:
            from vwmcp.trigger import default_trigger

            trigger = default_trigger(self.root)
        self.trigger = trigger
        self.timeout = timeout
        self.claim_timeout = claim_timeout
        self.poll_interval = poll_interval
        self.retrigger_after = RETRIGGER_AFTER
        self.alive_every = ALIVE_EVERY
        self._lock = threading.Lock()  # one job in flight: one trigger, one undo step
        self._seq = itertools.count()
        self.bridge_version: str | None = None  # learned from the first result
        self._libs: dict[str, dict] = {}
        self.last_timing: dict = {}
        self._housekept = 0.0

    # ------------------------------------------------------------ helpers

    def log(self, message: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().isoformat(timespec="seconds")
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {message}\n")

    def _new_job_id(self) -> str:
        # Zero-padded so the bridge's name sort is submission order.
        return f"{time.time_ns():020d}-{os.getpid()}-{next(self._seq):06d}"

    def supports_libs(self) -> bool:
        """The bridge in Vectorworks (version seen in its last result) caches
        helper libraries and checks the document named in a job (>= 0.2.0)."""
        return _version_tuple(self.bridge_version) >= (0, 2, 0)

    supports_guard = supports_libs

    def lib_ref(self, name: str, source: str) -> dict:
        """Reference to a helper library: written once to <root>/lib/<sha>.py;
        the bridge compiles it once per Vectorworks session."""
        sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
        path = self.libdir / f"{sha}.py"
        ref = self._libs.get(sha)
        if ref is None or not path.is_file():
            self.libdir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(source, encoding="utf-8")
            os.replace(tmp, path)
            ref = {"name": name, "sha": sha, "path": str(path)}
            self._libs[sha] = ref
        return ref

    def housekeep(self, now: float | None = None) -> int:
        """Remove leftovers: results nobody read, cancelled jobs, temp files
        older than an hour; helper libraries not used for a week."""
        now = time.time() if now is None else now
        removed = 0
        for folder, pattern in ((self.results, "*.json"), (self.results, "*.tmp"),
                                (self.jobs, "*.cancelled"), (self.jobs, "*.tmp")):
            for p in folder.glob(pattern) if folder.is_dir() else ():
                with contextlib.suppress(OSError):
                    if now - p.stat().st_mtime > STALE_AFTER:
                        p.unlink()
                        removed += 1
        if self.libdir.is_dir():
            for p in self.libdir.glob("*.py"):
                with contextlib.suppress(OSError):
                    if p.stem not in self._libs and now - p.stat().st_mtime > 7 * 86400:
                        p.unlink()
                        removed += 1
        self._housekept = now
        return removed

    # ---------------------------------------------------------------- run

    def run(self, code: str, timeout: float | None = None, libs: list[dict] | None = None,
            check: bool = True, document: dict | None = None, allow_dialogs: bool = False) -> dict:
        """Run code inside Vectorworks; return the bridge's result dict.
        libs: helper libraries (lib_ref) executed before the code.
        check: let the bridge check every vs.* call (types, safety).
        document: {"name", "path"}: the bridge refuses to run when another
        document is active (WrongDocument; nothing ran).
        allow_dialogs: permit vs.* functions that open a dialog."""
        timeout = self.timeout if timeout is None else timeout
        with self._lock:
            if time.time() - self._housekept > 600:
                with contextlib.suppress(OSError):
                    self.housekeep()
            res = self._run_locked(code, timeout, libs, check, document, allow_dialogs)
        err = res.get("error") or ""
        if err.startswith("WrongDocument:"):
            raise WrongDocument(err[len("WrongDocument:"):].strip())
        return res

    def _run_locked(self, code: str, timeout: float, libs: list[dict] | None, check: bool,
                    document: dict | None, allow_dialogs: bool) -> dict:
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.results.mkdir(parents=True, exist_ok=True)
        job_id = self._new_job_id()
        job_path = self.jobs / f"{job_id}.json"
        result_path = self.results / f"{job_id}.json"
        created = time.time()
        # ttl: the bridge refuses jobs older than this (orphans of a crashed
        # server); generous, so it never refuses a job we still wait for.
        job = {"id": job_id, "code": code, "created": created, "ttl": self.claim_timeout + 60,
               "protocol": 2}
        if libs:
            job["libs"] = libs
        if not check:
            job["check"] = False
        if document:
            job["document"] = document
        if allow_dialogs:
            job["allow_dialogs"] = True
        tmp = self.jobs / f"{job_id}.tmp"
        tmp.write_text(json.dumps(job), encoding="utf-8")
        os.replace(tmp, job_path)

        t0 = time.monotonic()
        try:
            self.trigger()
        except TriggerError as e:
            if self._cancel(job_path):
                self.log(f"trigger failed for job {job_id}: {e}")
                raise
            # Deliberate: a failed cancel means Vectorworks claimed the job
            # meanwhile (an earlier Apple Event, or another server), so wait
            # for its result instead of reporting the trigger error.

        # 1. wait for the claim (or a result, if it was quick)
        claimed_at = None
        last_fire = t0
        while claimed_at is None:
            if result_path.exists() or not job_path.exists():  # done, or renamed to .running
                claimed_at = time.monotonic()
                break
            now = time.monotonic()
            # wall clock too: monotonic time stands still while the Mac sleeps
            if now - t0 >= self.claim_timeout or time.time() - created >= self.claim_timeout:
                if self._cancel(job_path):
                    msg = self._not_claimed_message()
                    self.log(f"not claimed in {self.claim_timeout:g}s, cancelled {job_id}")
                    err = BridgeTimeout(msg)
                    err.never_ran = True
                    raise err
                claimed_at = now  # claimed right now: wait for the result
                break
            if now - last_fire >= self.retrigger_after and not self._trigger_in_flight():
                last_fire = now
                with contextlib.suppress(TriggerError):
                    self.trigger()
            time.sleep(self.poll_interval)

        # 2. wait for the result; stop early if Vectorworks is gone
        deadline = claimed_at + timeout
        alive = getattr(self.trigger, "target_alive", None)
        next_probe = claimed_at + self.alive_every
        while time.monotonic() < deadline:
            if result_path.exists():
                res = self._consume(result_path)
                self.bridge_version = res.get("bridge_version") or self.bridge_version
                self.last_timing = {"claim_s": round(claimed_at - t0, 3),
                                    "total_s": round(time.monotonic() - t0, 3),
                                    "vw_s": res.get("duration")}
                return res
            if callable(alive) and time.monotonic() >= next_probe:
                next_probe = time.monotonic() + self.alive_every
                if alive() is False and not result_path.exists():
                    msg = ("Vectorworks quit or restarted while working on this request; it did not "
                           "finish. Open Vectorworks with your document and check what was done.")
                    self.log(f"target gone, job {job_id}")
                    raise BridgeError(msg)
            time.sleep(self.poll_interval)

        msg = (f"Vectorworks is still working on this request after {timeout:g}s. It keeps "
               "running there; its result will be discarded. Check Vectorworks (vw_screenshot) "
               "and try again with a smaller request.")
        self.log(f"result timeout job {job_id}")
        raise BridgeTimeout(msg)

    def _trigger_in_flight(self) -> bool:
        probe = getattr(self.trigger, "in_flight", None)
        return bool(probe()) if callable(probe) else False

    def _not_claimed_message(self) -> str:
        return (f"Vectorworks did not pick up the job within {self.claim_timeout:g}s. Check that a "
                "document is open, no dialog or menu is open (a right-click menu left open also "
                "blocks it; vw_screenshot reports what is in front), and the 'MCP Run Job' menu "
                "command is in your workspace. The request was cancelled and will not run later.")

    def _cancel(self, job_path: Path) -> bool:
        """Rename an unclaimed job to .cancelled. True if it was still unclaimed
        (then it can never run); False if Vectorworks claimed it first."""
        try:
            os.replace(job_path, job_path.with_suffix(".cancelled"))
            return True
        except FileNotFoundError:
            return False

    def _consume(self, result_path: Path) -> dict:
        for attempt in range(5):
            try:
                res = json.loads(result_path.read_text(encoding="utf-8"))
                break
            except (json.JSONDecodeError, OSError):  # pragma: no cover - atomic writes
                if attempt == 4:
                    raise
                time.sleep(0.02)
        with contextlib.suppress(FileNotFoundError):
            result_path.unlink()
        return res
