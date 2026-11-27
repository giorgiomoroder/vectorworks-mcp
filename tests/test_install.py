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
    assert sorted(p.name for p in target.iterdir()) == [
        "__init__.py", "vs_safety.json", "vs_types.json", "vwmcp_bridge.py"]


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


def test_install_places_the_bundled_menu_command_once(tmp_path):
    target = tmp_path / "Plug-ins" / "vwmcp"
    msg = install.install_plugin(target)
    vsm = tmp_path / "Plug-ins" / install.MENU_COMMAND_FILE
    assert vsm.read_bytes() == install.bundled_menu_command().read_bytes()
    assert "Installed the 'MCP Run Job' menu command" in msg and "Edit Current Workspace" in msg
    vsm.write_bytes(b"user's own")
    msg = install.install_plugin(target)
    assert vsm.read_bytes() == b"user's own" and "already present" in msg


def test_install_without_a_menu_file_prints_the_script(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "bundled_menu_command", lambda: None)
    msg = install.install_plugin(tmp_path / "vwmcp")
    assert install.MENU_SCRIPT in msg and not (tmp_path / install.MENU_COMMAND_FILE).exists()


def test_install_copies_the_type_and_safety_tables(tmp_path):
    import json
    target = tmp_path / "Plug-ins" / "vwmcp"
    msg = install.install_plugin(target, menu_command=None)
    assert (target / "vs_types.json").is_file() and (target / "vs_safety.json").is_file()
    assert json.loads((target / "vs_types.json").read_text())["f"]["Rect"]["t"] == "PP"
    assert "tables" in msg


def test_install_on_windows_explains_mcp_listen(tmp_path, monkeypatch):
    from vwmcp import install
    monkeypatch.setattr(install, "bundled_listen_command", lambda: None)
    msg = install.install_plugin(tmp_path / "Plug-ins" / "vwmcp", platform="win32")
    assert "MCP Listen" in msg
    assert install.MENU_SCRIPT_LISTEN in msg


def test_install_on_macos_does_not_mention_listen(tmp_path):
    from vwmcp import install
    msg = install.install_plugin(tmp_path / "Plug-ins" / "vwmcp", platform="darwin")
    assert "MCP Listen" not in msg


def test_install_on_windows_places_the_bundled_listen_command_once(tmp_path):
    target = tmp_path / "Plug-ins" / "vwmcp"
    msg = install.install_plugin(target, platform="win32")
    dest = tmp_path / "Plug-ins" / "MCP Listen.vsm"
    assert dest.read_bytes() == install.bundled_listen_command().read_bytes()
    assert "Installed the 'MCP Listen' menu command" in msg
    assert "under Scripts" in msg
    assert install.MENU_SCRIPT_LISTEN not in msg  # no need to type it when the file is there
    msg2 = install.install_plugin(target, platform="win32")
    assert "Listen command already present" in msg2


def test_install_on_macos_does_not_place_the_listen_command(tmp_path):
    target = tmp_path / "Plug-ins" / "vwmcp"
    install.install_plugin(target, platform="darwin")
    assert not (tmp_path / "Plug-ins" / "MCP Listen.vsm").exists()


def test_install_on_windows_without_listen_file_prints_the_one_liner(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "bundled_listen_command", lambda: None)
    msg = install.install_plugin(tmp_path / "Plug-ins" / "vwmcp", platform="win32")
    assert install.MENU_SCRIPT_LISTEN in msg
    assert "\n" not in install.MENU_SCRIPT_LISTEN.strip()
