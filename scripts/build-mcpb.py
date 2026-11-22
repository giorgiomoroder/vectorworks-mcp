"""Build the Claude Desktop extension bundle: dist/vectorworks-mcp-<version>.mcpb

    uv run python scripts/build-mcpb.py [--out dist] [--validate]

An .mcpb is a zip with a manifest.json (MCP Bundle spec, manifest_version 0.4,
server type "uv": Claude Desktop installs the project with uv, so the user
needs no Python of their own). The bundle carries the server source, the
in-app bridge, pyproject.toml and uv.lock. The tools list in the manifest is
generated from the registered MCP tools so Claude Desktop can show them.
`--validate` runs `npx -y @anthropic-ai/mcpb validate` when node is around.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

NAME = "vectorworks-mcp"
# What goes into the bundle (paths relative to the repo root).
FILES = ["manifest.json", "pyproject.toml", "uv.lock", "README.md", "LICENSE", "mcpb_main.py"]
TREES = ["src/vwmcp", "vw-plugin/vwmcp", "skills"]
SKIP_DIRS = {"__pycache__"}


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


_ABBREVIATIONS = ("e.g.", "i.e.", "vs.", "etc.", "approx.", "min.", "max.")


def _first_sentence(text: str) -> str:
    """The first sentence: ends at . ! or ? followed by a space or the end,
    unless that period belongs to an abbreviation such as e.g. or i.e."""
    text = " ".join((text or "").split())
    for m in re.finditer(r"[.!?](?=\s|$)", text):
        end = m.end()
        if any(text[:end].endswith(a) for a in _ABBREVIATIONS):
            continue
        return text[:end][:280]
    return text[:280]


def tool_entries() -> list[dict]:
    from vwmcp.app import mcp
    from vwmcp.tools import drawing, generic, spotlight  # noqa: F401

    return [{"name": t.name, "description": _first_sentence(t.description)}
            for t in sorted(mcp._tool_manager.list_tools(), key=lambda t: t.name)]


def manifest() -> dict:
    return {
        "manifest_version": "0.4",
        "name": NAME,
        "display_name": "Vectorworks (Spotlight)",
        "version": project_version(),
        "description": "Lets Claude read and edit the open Vectorworks document: lighting devices, "
                       "positions, truss, stage decks, hookups, MVR pre-flight, screenshots.",
        "long_description": (
            "Mac-native MCP server for Vectorworks Spotlight (2026 and 2027). After installing, "
            "ask Claude to \"check the Vectorworks MCP setup\": it installs the small bridge into your "
            "Vectorworks Plug-ins folder. Then drag the 'MCP Run Job' command into a menu once "
            "(Tools > Workspaces > Edit Current Workspace > Menus) and restart Vectorworks. "
            "Every edit Claude makes can be reverted one call at a time."
        ),
        "author": {"name": "giorgiomoroder", "url": "https://github.com/giorgiomoroder"},
        "repository": {"type": "git", "url": "https://github.com/giorgiomoroder/vectorworks-mcp"},
        "homepage": "https://github.com/giorgiomoroder/vectorworks-mcp",
        "documentation": "https://github.com/giorgiomoroder/vectorworks-mcp#readme",
        "support": "https://github.com/giorgiomoroder/vectorworks-mcp/issues",
        "license": "MIT",
        "keywords": ["vectorworks", "spotlight", "lighting", "cad", "stage", "mvr"],
        "server": {
            "type": "uv",
            "entry_point": "mcpb_main.py",
            "mcp_config": {
                "command": "uv",
                "args": ["run", "--directory", "${__dirname}", "mcpb_main.py"],
                "env": {
                    "VWMCP_VW_VERSION": "${user_config.vw_version}",
                    "VWMCP_HOME": "${HOME}/.vwmcp",
                },
            },
        },
        "user_config": {
            "vw_version": {
                "type": "string",
                "title": "Vectorworks version",
                "description": "The year of the Vectorworks you want Claude to work in, e.g. 2026 or 2027. "
                               "One extension talks to one version.",
                "default": "2026",
                "required": True,
            },
        },
        "compatibility": {
            "platforms": ["darwin"],
            "runtimes": {"python": ">=3.11"},
        },
        "tools": tool_entries(),
        "tools_generated": False,
    }


def stage(staging: Path) -> None:
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    (staging / "manifest.json").write_text(json.dumps(manifest(), indent=2) + "\n", encoding="utf-8")
    for rel in FILES[1:]:
        src = ROOT / rel
        if src.exists():
            shutil.copy2(src, staging / rel)
    for rel in TREES:
        shutil.copytree(ROOT / rel, staging / rel,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))


def build(out_dir: Path | None = None, validate: bool = False) -> Path:
    out_dir = Path(out_dir) if out_dir else ROOT / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    staging = out_dir / f"{NAME}-mcpb"
    stage(staging)
    if validate:
        subprocess.run(["npx", "-y", "@anthropic-ai/mcpb", "validate", str(staging / "manifest.json")], check=True)
    out = out_dir / f"{NAME}-{project_version()}.mcpb"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(p for p in staging.rglob("*") if p.is_file()):
            z.write(path, path.relative_to(staging).as_posix())
    shutil.rmtree(staging)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None)
    ap.add_argument("--validate", action="store_true")
    a = ap.parse_args()
    print(build(Path(a.out) if a.out else None, validate=a.validate))
