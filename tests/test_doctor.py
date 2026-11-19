import json
import os
import time

from vwmcp import app, doctor, install


def setup_home(tmp_path, bridge_version=None, desktop=True, code=True):
    home = tmp_path / "home"
    if bridge_version:
        target = install.plugin_dir("2026", platform="darwin", home=home)
        install.install_plugin(target)
        if bridge_version != app.EXPECTED_BRIDGE_VERSION:
            p = target / "vwmcp_bridge.py"
            p.write_text(p.read_text().replace(app.EXPECTED_BRIDGE_VERSION, bridge_version))
    entry = {"mcpServers": {"vectorworks": {"command": "/bin/sh", "args": ["x"]}}}
    if desktop:
        cfg = doctor.claude_desktop_config(home, "darwin")
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps(entry))
    if code:
        (home / ".claude.json").write_text(json.dumps(entry))
    return home


def run(home, root, **kw):
    kw.setdefault("uptime", lambda: 600)
    kw.setdefault("platform", "darwin")
    return {c.name: c for c in doctor.run_checks(home=home, root=root, **kw)}


def test_all_good(tmp_path):
    home = setup_home(tmp_path, bridge_version=app.EXPECTED_BRIDGE_VERSION)
    checks = run(home, home / ".vwmcp")
    assert all(c.ok for c in checks.values()), {n: c.detail for n, c in checks.items()}
    assert "/bin/sh x" in checks["claude_desktop"].detail


def test_bridge_missing_and_outdated(tmp_path):
    home = setup_home(tmp_path)
    assert run(home, tmp_path / "r")["bridge"].ok is False
    home = setup_home(tmp_path / "b", bridge_version="0.0.1")
    c = run(home, tmp_path / "r")["bridge"]
    assert c.ok is False and "0.0.1" in c.detail and "install-plugin" in c.fix


def test_claude_configs(tmp_path):
    home = setup_home(tmp_path, desktop=False, code=False)
    checks = run(home, tmp_path / "r")
    assert checks["claude_desktop"].ok is None
    assert checks["claude_code"].ok is None and "not set up" in checks["claude_code"].detail
    cfg = doctor.claude_desktop_config(home, "darwin")
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"mcpServers": {"other": {}}}))
    assert run(home, tmp_path / "r")["claude_desktop"].ok is False
    cfg.write_text(json.dumps({"mcpServers": {"vectorworks": {"command": "/nope/uvx"}}}))
    assert "does not exist" in run(home, tmp_path / "r")["claude_desktop"].detail


def test_vectorworks_process(tmp_path):
    home = setup_home(tmp_path)
    assert "not running" in run(home, tmp_path / "r", uptime=lambda: None)["vectorworks"].detail
    assert run(home, tmp_path / "r", uptime=lambda: 5)["vectorworks"].ok is False
    assert run(home, tmp_path / "r", platform="win32", uptime=lambda: None)["vectorworks"].ok is None


def test_runtime_stale_files_reported_and_fixed(tmp_path):
    home = setup_home(tmp_path)
    root = tmp_path / "vwmcp"
    (root / "results").mkdir(parents=True)
    (root / "jobs").mkdir()
    old = time.time() - 2 * 3600
    stale = root / "results" / "old.json"
    stale.write_text("{}")
    os.utime(stale, (old, old))
    fresh = root / "results" / "new.json"
    fresh.write_text("{}")
    job = root / "jobs" / "stuck.json"
    job.write_text("{}")
    os.utime(job, (old, old))
    c = run(home, root)["runtime"]
    assert c.ok and "1 stale results, 1 stale jobs" in c.detail and "--fix" in c.fix
    c = run(home, root, fix=True)["runtime"]
    assert "removed 1 stale results, 1 stale jobs" in c.detail
    assert not stale.exists() and fresh.exists() and not job.exists()


def test_log_summary(tmp_path):
    home = setup_home(tmp_path)
    root = tmp_path / "vwmcp"
    root.mkdir()
    now = time.time()
    recent = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - 60))
    (root / "vwmcp.log").write_text(
        f"2020-01-01T00:00:00 trigger failed for job 1: old\n{recent} timeout job 2: dialog open\n"
    )
    c = run(home, root, now=now)["log"]
    assert "1 errors in the last 24 h" in c.detail and "dialog open" in c.detail


def test_report_format(tmp_path):
    home = setup_home(tmp_path, bridge_version=app.EXPECTED_BRIDGE_VERSION)
    text = doctor.format_report(doctor.run_checks(home=home, root=home / ".vwmcp", uptime=lambda: None, platform="darwin"))
    assert "FAIL vectorworks" in text and "ok   bridge" in text and "MCP Run Job" in text


def test_bridge_home_file_must_match_server_root(tmp_path):
    home = setup_home(tmp_path, bridge_version=app.EXPECTED_BRIDGE_VERSION)
    root = tmp_path / "vwmcp-2027"
    c = run(home, root)["bridge"]  # bridge has no home file: it serves ~/.vwmcp, not this root
    assert c.ok is False and "runs jobs from" in c.detail and f"--home {root}" in c.fix
    target = install.plugin_dir("2026", platform="darwin", home=home)
    install.install_plugin(target, home=root)
    c = run(home, root)["bridge"]
    assert c.ok is True and f"jobs from {root}" in c.detail
    assert run(home, home / ".vwmcp")["bridge"].ok is False
