"""The bundled skill (skills/vectorworks-spotlight/SKILL.md) must stay truthful."""

import re
from pathlib import Path

from vwmcp import mvr
from vwmcp.app import mcp
from vwmcp.tools import drawing, generic, spotlight  # noqa: F401  (registers the tools)

SKILL = Path(__file__).resolve().parents[1] / "skills" / "vectorworks-spotlight" / "SKILL.md"


def test_skill_has_frontmatter():
    text = SKILL.read_text(encoding="utf-8")
    head = text.split("---")[1]
    assert re.search(r"^name: vectorworks-spotlight$", head, re.M)
    assert re.search(r"^description: .{40,}", head, re.M)


def test_every_tool_named_in_the_skill_exists():
    text = SKILL.read_text(encoding="utf-8")
    registered = {t.name for t in mcp._tool_manager.list_tools()}
    named = set(re.findall(r"\bvw_[a-z0-9_]+", text))
    assert named, "skill names no tools"
    assert named - registered == set()


def test_skill_covers_the_session_start_and_safety_rules():
    text = SKILL.read_text(encoding="utf-8")
    for must in ("vw_list_documents", "document=", "vw_revert_last", "vw_screenshot",
                 "vw_mvr_check", "vw_import_hookup", "vw_doctor", "Script Errors"):
        assert must in text, must


def test_skill_uses_the_real_mvr_check_names():
    text = SKILL.read_text(encoding="utf-8")
    mentioned = set(re.findall(r"`([a-z_0-9]+)`", text))
    for check in ("no_gdtf", "no_fixture_id", "unpatched", "address_overlap"):
        assert check in mentioned, check
    assert mentioned & set(mvr.NEEDS) <= set(mvr.NEEDS)
