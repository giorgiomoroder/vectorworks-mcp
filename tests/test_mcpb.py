"""Claude Desktop extension bundle (.mcpb): manifest and contents."""

import json
import zipfile
from pathlib import Path

import pytest

from vwmcp.app import mcp
from vwmcp.tools import drawing, generic, spotlight  # noqa: F401

import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_mcpb", ROOT / "scripts" / "build-mcpb.py")
build_mcpb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_mcpb)


def test_manifest_matches_pyproject_and_spec():
    m = build_mcpb.manifest()
    assert m["manifest_version"] == "0.4"
    assert m["name"] == "vectorworks-mcp"
    assert m["version"] == build_mcpb.project_version()
    assert m["server"]["type"] == "uv"
    assert m["server"]["entry_point"] == "mcpb_main.py"
    assert m["server"]["mcp_config"]["command"] == "uv"
    assert "${__dirname}" in m["server"]["mcp_config"]["args"]
    assert m["server"]["mcp_config"]["env"]["VWMCP_VW_VERSION"] == "${user_config.vw_version}"
    assert m["user_config"]["vw_version"]["default"] == "2026"
    assert m["compatibility"]["platforms"] == ["darwin"]
    for key in ("description", "author", "license", "repository"):
        assert key in m


def test_manifest_lists_every_registered_tool():
    names = {t["name"] for t in build_mcpb.manifest()["tools"]}
    assert names == {t.name for t in mcp._tool_manager.list_tools()}
    for t in build_mcpb.manifest()["tools"]:
        assert t["description"] and len(t["description"]) < 300


def test_bundle_contains_server_and_bridge_but_no_tests(tmp_path):
    out = build_mcpb.build(out_dir=tmp_path)
    assert out.name == f"vectorworks-mcp-{build_mcpb.project_version()}.mcpb"
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        manifest = json.loads(z.read("manifest.json"))
    assert {"manifest.json", "pyproject.toml", "README.md", "LICENSE", "mcpb_main.py",
            "src/vwmcp/server.py", "src/vwmcp/vwlib.py", "src/vwmcp/menu/MCP Run Job.vsm",
            "src/vwmcp/data/vs_api_2027.json", "vw-plugin/vwmcp/vwmcp_bridge.py"} <= names
    assert not any(n.startswith(("tests/", "docs/", "scripts/", ".github/")) for n in names)
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)
    assert manifest["version"] == build_mcpb.project_version()


def test_entry_point_runs_the_server_main():
    text = (ROOT / "mcpb_main.py").read_text(encoding="utf-8")
    assert "from vwmcp.server import main" in text
    assert "3, 11" in text  # friendly message on an old Python
