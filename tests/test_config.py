from pathlib import Path

from vwmcp import config


def apps(tmp_path, *years):
    root = tmp_path / "Applications"
    for y in years:
        (root / f"Vectorworks {y}" / f"Vectorworks {y}.app").mkdir(parents=True)
    (root / "Vectorworks 2022 Viewer").mkdir(exist_ok=True)  # no .app inside, not a version
    return root


def test_installed_versions_sorted(tmp_path):
    assert config.installed_versions(apps(tmp_path, "2027", "2026")) == ["2026", "2027"]
    assert config.installed_versions(tmp_path / "none") == []


def test_detect_version_precedence(tmp_path):
    both = apps(tmp_path, "2026", "2027")
    assert config.detect_version({"VWMCP_VW_VERSION": "2025", "VWMCP_APP": "Vectorworks 2027"}, both) == "2025"
    assert config.detect_version({"VWMCP_APP": "Vectorworks 2027"}, both) == "2027"
    assert config.detect_version({}, both) == "2026"  # several installed: assume the default
    only = apps(tmp_path / "one", "2027")
    assert config.detect_version({}, only) == "2027"
    assert config.detect_version({}, tmp_path / "none") == "2026"


def test_tools_off_groups():
    assert config.tools_off({}) == []
    off = config.tools_off({"VWMCP_TOOLS_OFF": "spotlight, Stage,unknown"})
    assert "vw_list_lighting_devices" in off and "vw_insert_truss_run" in off
    assert "vw_export_geometry" not in off and "vw_ping" not in off


def test_every_grouped_tool_exists():
    from vwmcp.app import mcp
    from vwmcp.tools import drawing, generic, spotlight  # noqa: F401

    names = {t.name for t in mcp._tool_manager.list_tools()}
    for group, tools in config.TOOL_GROUPS.items():
        missing = set(tools) - names
        assert not missing, (group, missing)
