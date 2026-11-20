"""vwmcp bridge: the in-Vectorworks half of vectorworks-mcp.

A checked executor. Each call to run_pending() claims the oldest job in
<root>/jobs/, exec()s its Python source with `vs` in scope, and writes
<root>/results/<id>.json. All real logic lives in the MCP server.

Since 0.2.0 the `vs` the job sees is a proxy: every vs.* call is checked
against the signature table (vs_types.json beside this file: argument count
and types) and the safety table (vs_safety.json: functions known to crash
or hang Vectorworks, or to open a dialog). A bad call raises an ordinary
Python error that lands in the result, instead of Vectorworks showing the
modal "Script Errors" dialog that blocks every further job until someone
clicks OK. Only functions whose live docstring agrees with the table on the
parameter count are type-checked, so a Vectorworks whose API changed is
simply not checked rather than checked wrongly.

On macOS the server triggers run_pending() via AppleScript running a
VectorScript that calls the "MCP Run Job" menu command, so nothing here
ever loops or blocks the UI. One job per call keeps one tool call == one
Vectorworks undo step.

Must stay Python 3.9 (Vectorworks 2026). Keep this file dependency-free;
bump BRIDGE_VERSION whenever the job/result format changes.
"""

import ast
import contextlib
import hashlib
import io
import json
import os
import re
import sys
import time
import traceback
import types

BRIDGE_VERSION = "0.2.0"
DEFAULT_ROOT = os.path.join(os.path.expanduser("~"), ".vwmcp")
# Written by `vwmcp install-plugin --home`: lets each Vectorworks version run
# its own server's jobs when several versions are installed side by side.
HOME_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vwmcp_home.txt")
TYPES_FILE = "vs_types.json"    # both installed beside this file by `vwmcp install-plugin`
SAFETY_FILE = "vs_safety.json"
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # pragma: no cover - exec'd without a file
    _HERE = None
# Survives importlib.reload(): tables and compiled libraries built this session.
_CACHE = globals().get("_CACHE") or {"tables": None, "tables_key": None, "libs": {}}


def configured_root():
    try:
        with open(HOME_FILE, encoding="utf-8") as f:
            text = f.read().strip()
    except OSError:
        return DEFAULT_ROOT
    return os.path.expanduser(text) if text else DEFAULT_ROOT


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


# ------------------------------------------------------------- checked vs


class VSArgumentError(TypeError):
    """A vs.* call whose arguments don't fit its signature. Raised before
    Vectorworks sees the call: it would show the modal Script Errors dialog
    and block every further job until someone clicks OK."""


class VSUnsafeError(RuntimeError):
    """A vs.* function known to crash or hang Vectorworks, or to open a dialog
    (refused unless the job allows dialogs)."""


_NUMBER = (int, float)
_TUPLE_LEN = {"P": (2, 3), "Q": (2, 3), "V": (2, 3), "C": (3,)}
_WIDTH = {"P": 2, "Q": 3, "V": 3}
_TYPE_NAME = {"H": "HANDLE", "R": "REAL", "I": "INTEGER", "B": "BOOLEAN", "S": "STRING",
              "P": "POINT", "Q": "POINT3D", "V": "VECTOR", "C": "COLOR", "F": "callback"}
# re.S: live docstrings put "Definition:" and the signature on different lines.
_DEFINITION = re.compile(r"Definition:.*?vs\.\w+\s*\(([^)]*)\)", re.S)


def _live_param_count(fn):
    """Parameter count from Vectorworks' own docstring; None without one."""
    m = _DEFINITION.search(getattr(fn, "__doc__", None) or "")
    if not m:
        return None
    inner = m.group(1).strip()
    return len([p for p in inner.split(",") if p.strip()]) if inner else 0


def _has_var_args(fn):
    code = getattr(fn, "__code__", None)
    return bool(code is not None and code.co_flags & 0x04)


def check_args(codes, args):
    """None if args fit the type codes, else a short description of the problem.
    Conservative: whatever Vectorworks might accept passes (a tuple of numbers
    may also stand for consecutive number parameters)."""
    i, n, k = 0, len(args), 0
    while k < len(codes):
        c = codes[k]
        pos = k + 1
        if c in _TUPLE_LEN:
            if i < n and isinstance(args[i], (tuple, list)):
                if len(args[i]) not in _TUPLE_LEN[c]:
                    return "parameter %d (%s) needs %s values, got a tuple of %d" % (
                        pos, _TYPE_NAME[c], " or ".join(str(x) for x in _TUPLE_LEN[c]), len(args[i]))
                i += 1
                k += 1
                continue
            if c == "C":
                return ("parameter %d (COLOR) must be one tuple (r, g, b); loose numbers are "
                        "ignored silently by Vectorworks" % pos)
            w = _WIDTH[c]
            loose = args[i:i + w]
            if len(loose) < w or not all(isinstance(a, _NUMBER) for a in loose):
                return "parameter %d (%s) needs a tuple or %d numbers" % (pos, _TYPE_NAME[c], w)
            i += w
            k += 1
            continue
        if i >= n:
            return "too few arguments (%d given)" % n
        a = args[i]
        if c in "RIB" and isinstance(a, str):
            return "parameter %d (%s) got text %r" % (pos, _TYPE_NAME[c], a[:40])
        if c in "RI" and isinstance(a, (tuple, list)):
            span = codes[k:k + len(a)]
            if len(a) > 1 and len(span) == len(a) and all(x in "RIB" for x in span):
                i += 1  # one tuple covering consecutive number parameters
                k += len(a)
                continue
            return "parameter %d (%s) got a tuple of %d" % (pos, _TYPE_NAME[c], len(a))
        if c == "H" and isinstance(a, str):
            return ("parameter %d (HANDLE) got text %r; for a UUID use "
                    "vs.GetObjectByUuid(uuid)" % (pos, a[:40]))
        if c == "F":
            if not callable(a):
                return "parameter %d (callback) is not callable" % pos
            if _has_var_args(a):
                return ("parameter %d (callback) uses *args; Vectorworks counts named parameters, "
                        "declare them explicitly (e.g. def f(h))" % pos)
        i += 1
        k += 1
    if i != n:
        return "too many arguments (%d given)" % n
    return None


def _unwrap(a):
    """A proxied vs function passed as an argument (vs.ForEachObject(vs.SetSelect,
    ...)) goes to Vectorworks as the original built-in."""
    return getattr(a, "__wrapped__", a) if getattr(a, "_vwmcp_checked", False) else a


def _make_checked(name, fn, spec, safety, allow_dialogs):
    codes, params = spec if spec else (None, "")
    reason = safety.get(name)

    def checked(*args, **kwargs):
        if reason == "crash":
            raise VSUnsafeError("vs.%s not called: it crashes Vectorworks (safety sweep)" % name)
        if reason == "hang":
            raise VSUnsafeError("vs.%s not called: it hangs Vectorworks (safety sweep)" % name)
        if reason == "interactive" and not allow_dialogs:
            raise VSUnsafeError("vs.%s not called: it opens a dialog that blocks every further "
                                "job; pass allow_dialogs=True if you really want it" % name)
        if args and any(getattr(a, "_vwmcp_checked", False) for a in args):
            args = tuple(_unwrap(a) for a in args)
        if kwargs and any(getattr(v, "_vwmcp_checked", False) for v in kwargs.values()):
            kwargs = dict((k, _unwrap(v)) for k, v in kwargs.items())
        if codes is not None and not kwargs:
            problem = check_args(codes, args)
            if problem is not None:
                raise VSArgumentError("vs.%s not called: %s. Signature: vs.%s(%s)%s" % (
                    name, problem, name, params,
                    "  [POINT = (x, y) or x, y]" if "P" in codes else ""))
        return fn(*args, **kwargs)

    checked.__name__ = name
    checked.__qualname__ = name
    checked.__doc__ = getattr(fn, "__doc__", None)
    checked.__wrapped__ = fn
    checked._vwmcp_checked = True
    return checked


class CheckedVS(types.ModuleType):
    """Stands in for the `vs` module during a job: every function call is
    checked against the type table and the safety list first."""

    def __init__(self, real, tables, allow_dialogs=False):
        types.ModuleType.__init__(self, "vs", getattr(real, "__doc__", None))
        object.__setattr__(self, "_vw_real", real)
        object.__setattr__(self, "_vw_tables", tables)
        object.__setattr__(self, "_vw_dialogs", allow_dialogs)

    def __getattr__(self, name):
        real = object.__getattribute__(self, "_vw_real")
        value = getattr(real, name)  # AttributeError as usual
        tables = object.__getattribute__(self, "_vw_tables")
        spec = tables["types"].get(name)
        if callable(value) and (spec is not None or name in tables["safety"]):
            value = _make_checked(name, value, spec, tables["safety"],
                                  object.__getattribute__(self, "_vw_dialogs"))
        object.__setattr__(self, name, value)  # cache for this job
        return value

    def __dir__(self):
        return dir(object.__getattribute__(self, "_vw_real"))


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_tables(vs_module, here=None):
    """{"types": {name: (codes, params)}, "safety": {name: reason}} from the
    json files beside this bridge. A function is type-checked only when the
    live docstring's parameter count agrees with the table (the live API wins).
    Cached per file mtimes and vs module; empty tables when the files are missing."""
    here = here or _HERE
    if not here:
        return {"types": {}, "safety": {}}
    tp, sp = os.path.join(here, TYPES_FILE), os.path.join(here, SAFETY_FILE)
    key = (tuple(os.path.getmtime(p) if os.path.isfile(p) else None for p in (tp, sp)), id(vs_module))
    if _CACHE["tables_key"] == key and _CACHE["tables"] is not None:
        return _CACHE["tables"]
    types_table = {}
    for name, entry in (((_read_json(tp) or {}).get("f")) or {}).items():
        codes = entry.get("t")
        if codes is None:
            continue
        fn = getattr(vs_module, name, None)
        if fn is None or not callable(fn):
            continue
        live = _live_param_count(fn)
        if live is None or live != len(codes):
            continue
        types_table[name] = (codes, entry.get("a", ""))
    safety = {}
    for reason, names in (_read_json(sp) or {}).items():
        if reason in ("crash", "hang", "interactive"):
            for n in names:
                safety[n] = reason
    tables = {"types": types_table, "safety": safety}
    _CACHE["tables"], _CACHE["tables_key"] = tables, key
    return tables


# ----------------------------------------------------------------- running


def _compiled_lib(lib):
    """Compiled code of a helper library {"name", "sha", "path"} (or "src"),
    cached by sha for the whole Vectorworks session (the imported bridge
    module lives as long as the app)."""
    sha = lib.get("sha")
    code = _CACHE["libs"].get(sha) if sha else None
    if code is not None:
        return code
    src = lib.get("src")
    if src is None:
        with open(lib["path"], encoding="utf-8") as f:
            src = f.read()
    if sha and hashlib.sha256(src.encode("utf-8")).hexdigest() != sha:
        raise RuntimeError("helper library %s does not match its checksum" % lib.get("path"))
    code = compile(src, "<%s>" % lib.get("name", "lib"), "exec")
    if sha:
        if len(_CACHE["libs"]) > 16:
            _CACHE["libs"].clear()
        _CACHE["libs"][sha] = code
    return code


def _execute(code, vs_module, libs=()):
    """Run code after the helper libraries; return the value: the last
    expression unless the code assigns `result`."""
    scope = {"vs": vs_module, "__name__": "__vwmcp__"}
    for lib in libs:
        exec(_compiled_lib(lib), scope)
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
    """Atomically claim the oldest job by renaming it; returns the claimed path.
    The rename loses against the server's cancel rename (.cancelled), so a
    job the server gave up on never runs."""
    try:
        names = [n for n in os.listdir(jobs_dir) if n.endswith(".json")]
    except FileNotFoundError:
        return None
    names.sort()  # job ids are time-prefixed by the server
    for name in names:
        src = os.path.join(jobs_dir, name)
        dst = src[: -len(".json")] + ".running"
        try:
            os.replace(src, dst)
            return dst
        except FileNotFoundError:
            continue
    return None


def _doc_key(name):
    import unicodedata
    s = unicodedata.normalize("NFC", name or "").strip()
    if s.lower().endswith(".vwx"):
        s = s[:-4]
    return s.casefold()


def _wrong_document(vs_module, want):
    """Error text if the active document is not `want` ({"name", "path"}),
    else None. The path decides when both sides have one; else the name
    (case, .vwx and Unicode form do not matter). Checked right before the
    job runs, because the user may switch documents between two jobs."""
    try:
        name = str(vs_module.GetFName() or "")
    except Exception:  # noqa: BLE001
        name = ""
    try:
        path = str(vs_module.GetFPathName() or "") if hasattr(vs_module, "GetFPathName") else ""
    except Exception:  # noqa: BLE001
        path = ""
    want_path, want_name = want.get("path") or "", want.get("name") or ""
    if want_path and path and _doc_key(path) != _doc_key(name):
        ok = _doc_key(path) == _doc_key(want_path)
    else:
        ok = _doc_key(name) == _doc_key(want_name or os.path.basename(want_path))
    if ok:
        return None
    return "WrongDocument: the active document is %r, not %r; nothing was run" % (
        name or path, want_name or want_path)


def _run_job(job, res, out, vs_module):
    """Execute one loaded job into `res` (the checked vs, stdout captured)."""
    want = job.get("document")
    problem = _wrong_document(vs_module, want) if want else None
    if problem:
        res["error"] = problem
        res["never_ran"] = True
        return
    run_vs, proxy, saved_vs = vs_module, None, None
    if job.get("check", True):
        try:
            tables = load_tables(vs_module)
            if tables["types"] or tables["safety"]:
                run_vs = proxy = CheckedVS(vs_module, tables, bool(job.get("allow_dialogs")))
        except Exception as e:  # checking is a safety net, never a blocker
            res["warning"] = "argument check unavailable: %s: %s" % (type(e).__name__, e)
    if proxy is not None:
        saved_vs = sys.modules.get("vs")
        sys.modules["vs"] = proxy  # `import vs` inside the job gets the proxy too
    try:
        with contextlib.redirect_stdout(out):
            value = _execute(job["code"], run_vs, job.get("libs") or ())
    finally:
        if proxy is not None:
            if saved_vs is None:
                sys.modules.pop("vs", None)
            else:
                sys.modules["vs"] = saved_vs
    res["ok"] = True
    res["value"] = _jsonable(value)


def run_pending(root=None, vs_module=None, max_jobs=1):
    """Run up to max_jobs queued jobs. Returns the number run. `root` defaults
    to the folder named in vwmcp_home.txt beside this file, else ~/.vwmcp."""
    if vs_module is None:
        import vs as vs_module  # only importable inside Vectorworks
    root = str(configured_root() if root is None else root)
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
        started = time.time()
        res = {"id": job_id, "ok": False, "value": None, "stdout": "",
               "error": None, "traceback": None, "bridge_version": BRIDGE_VERSION,
               "claimed_at": started}
        try:
            with open(claimed, encoding="utf-8") as f:
                job = json.load(f)
            ttl = job.get("ttl")
            if ttl is not None and started - job.get("created", started) > ttl:
                res["error"] = "job expired before Vectorworks picked it up"
                res["never_ran"] = True
            else:
                _run_job(job, res, out, vs_module)
        except BaseException as e:  # noqa: BLE001 - report everything, never crash VW
            res["error"] = "%s: %s" % (type(e).__name__, e)
            res["traceback"] = traceback.format_exc()
        res["stdout"] = out.getvalue()
        res["duration"] = round(time.time() - started, 4)
        _write_json_atomic(os.path.join(results_dir, job_id + ".json"), res)
        with contextlib.suppress(FileNotFoundError):
            os.remove(claimed)
    return ran
