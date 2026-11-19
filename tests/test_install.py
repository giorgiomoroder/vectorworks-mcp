from vwmcp import app, install


def test_plugin_dir_macos(tmp_path):
    d = install.plugin_dir("2026", platform="darwin", home=tmp_path)
    assert d == tmp_path / "Library/Application Support/Vectorworks/2026/Plug-ins/vwmcp"


def test_plugin_dir_windows(tmp_path):
    d = install.plugin_dir("2026", platform="win32", appdata=tmp_path)
    assert d == tmp_path / "Nemetschek/Vectorworks/2026/Plug-ins/vwmcp"


def test_install_writes_package_and_reports_version(tmp_path):
    target = tmp_path / "Plug-ins" / "vwmcp"
    msg = install.install_plugin(target)
    assert (target / "vwmcp_bridge.py").read_text() == app.bundled_bridge_source()
    assert (target / "__init__.py").exists()
    assert app.EXPECTED_BRIDGE_VERSION in msg


def test_install_is_idempotent(tmp_path):
    target = tmp_path / "vwmcp"
    install.install_plugin(target)
    install.install_plugin(target)
    assert sorted(p.name for p in target.iterdir()) == ["__init__.py", "vwmcp_bridge.py"]


def test_install_writes_home_file_only_when_given(tmp_path):
    target = tmp_path / "vwmcp"
    msg = install.install_plugin(target, home="/Users/x/.vwmcp-2027")
    assert (target / "vwmcp_home.txt").read_text().strip() == "/Users/x/.vwmcp-2027"
    assert ".vwmcp-2027" in msg
    install.install_plugin(target)  # reinstall without --home: back to the default folder
    assert not (target / "vwmcp_home.txt").exists()


def test_plugin_dir_default_version_follows_env(monkeypatch, tmp_path):
    import importlib
    from vwmcp import config
    monkeypatch.setenv("VWMCP_VW_VERSION", "2027")
    monkeypatch.delenv("VWMCP_APP", raising=False)
    importlib.reload(config)
    try:
        assert config.VW_VERSION == "2027" and config.DEFAULT_APP == "Vectorworks 2027"
    finally:
        monkeypatch.delenv("VWMCP_VW_VERSION")
        importlib.reload(config)
    assert config.DEFAULT_APP == "Vectorworks 2026"
