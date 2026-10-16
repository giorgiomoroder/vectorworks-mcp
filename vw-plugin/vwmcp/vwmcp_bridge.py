"""vwmcp bridge: the in-Vectorworks half of vectorworks-mcp.

A dumb executor. Each call to run_pending() claims the oldest job in
<root>/jobs/, exec()s its Python source with `vs` in scope, and writes
<root>/results/<id>.json. All real logic lives in the MCP server.

On macOS the server triggers run_pending() via AppleScript
(`run Python script`), so nothing here ever loops or blocks the UI.
One job per call keeps one tool call == one Vectorworks undo step.

Keep this file small and dependency-free; bump BRIDGE_VERSION whenever
the job/result format changes.
"""

import ast
import contextlib
import io
import json
import os
import time
import traceback

BRIDGE_VERSION = "0.1.0"
DEFAULT_ROOT = os.path.join(os.path.expanduser("~"), ".vwmcp")


def _write_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, default=repr)
    os.replace(tmp, path)


def _jsonable(value):
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


def _execute(code, vs_module):
    """Run code; return (value, error, traceback). Last expression is the value
    unless the code assigns `result`."""
    scope = {"vs": vs_module, "__name__": "__vwmcp__"}
    tree = ast.parse(code, "<vwmcp job>", "exec")
    last_expr = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last_expr = ast.Expression(tree.body.pop().value)
    exec(compile(tree, "<vwmcp job>", "exec"), scope)
    value = None
    if last_expr is not None:
        value = eval(compile(last_expr, "<vwmcp job>", "eval"), scope)
    if "result" in scope:
        value = scope["result"]
    return value


def _claim_oldest(jobs_dir):
    """Atomically claim the oldest job by renaming it; returns the claimed path."""
    try:
        names = [n for n in os.listdir(jobs_dir) if n.endswith(".json")]
    except FileNotFoundError:
        return None
    names.sort()  # job ids are time-prefixed by the server
    for name in names:
        src = os.path.join(jobs_dir, name)
        dst = src[: -len(".json")] + ".running"
        try:
            os.replace(src, dst)  # the server deletes unclaimed jobs on timeout
            return dst
        except FileNotFoundError:
            continue
    return None


def run_pending(root=DEFAULT_ROOT, vs_module=None, max_jobs=1):
    """Run up to max_jobs queued jobs. Returns the number run."""
    if vs_module is None:
        import vs as vs_module  # only importable inside Vectorworks
    root = str(root)
    jobs_dir = os.path.join(root, "jobs")
    results_dir = os.path.join(root, "results")
    os.makedirs(results_dir, exist_ok=True)

    ran = 0
    while ran < max_jobs:
        claimed = _claim_oldest(jobs_dir)
        if claimed is None:
            break
        ran += 1
        job_id = os.path.basename(claimed)[: -len(".running")]
        out = io.StringIO()
        res = {"id": job_id, "ok": False, "value": None, "stdout": "",
               "error": None, "traceback": None, "bridge_version": BRIDGE_VERSION}
        started = time.time()
        try:
            with open(claimed, encoding="utf-8") as f:
                job = json.load(f)
            ttl = job.get("ttl")
            if ttl is not None and started - job.get("created", started) > ttl:
                res["error"] = "job expired before Vectorworks picked it up"
            else:
                with contextlib.redirect_stdout(out):
                    value = _execute(job["code"], vs_module)
                res["ok"] = True
                res["value"] = _jsonable(value)
        except BaseException as e:  # noqa: BLE001 - report everything, never crash VW
            res["error"] = "%s: %s" % (type(e).__name__, e)
            res["traceback"] = traceback.format_exc()
        res["stdout"] = out.getvalue()
        res["duration"] = round(time.time() - started, 4)
        _write_json_atomic(os.path.join(results_dir, job_id + ".json"), res)
        with contextlib.suppress(FileNotFoundError):
            os.remove(claimed)
    return ran
