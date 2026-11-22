"""Tool definitions as an agent sees them (Glama's TDQS lint, 2026-11-21:
every parameter needs a schema description; names follow vw_<verb>_<thing>)."""

import re

from vwmcp.server import mcp  # noqa: F401  (registers every tool)
from vwmcp.app import mcp as app_mcp


def _tools():
    return list(app_mcp._tool_manager.list_tools())


def test_every_parameter_has_a_description():
    missing = []
    for t in _tools():
        props = t.parameters.get("properties", {})
        for name, schema in props.items():
            if not str(schema.get("description", "")).strip():
                missing.append(f"{t.name}.{name}")
    assert not missing, "parameters without a description:\n" + "\n".join(missing)


def test_every_tool_has_a_description_of_a_useful_length():
    short = [t.name for t in _tools() if len((t.description or "").strip()) < 80]
    assert not short, f"descriptions under 80 characters: {short}"


def test_tool_names_follow_the_verb_thing_pattern():
    bad = [t.name for t in _tools() if not re.fullmatch(r"vw_[a-z]+(_[a-z0-9]+)*", t.name)]
    assert not bad, bad


def test_merged_tools_are_gone_and_the_count_is_50():
    # 2026-11-21 consolidation: plug-in parameters are records (vw_get_record /
    # vw_set_record with record omitted), a script file is vw_exec_python(path=),
    # the two library tools are vw_list_library.
    names = {t.name for t in _tools()}
    assert not names & {"vw_get_pio_parameters", "vw_set_pio_parameters", "vw_exec_file",
                        "vw_list_library_files", "vw_list_library_resources"}
    assert {"vw_list_library", "vw_get_record", "vw_set_record", "vw_exec_python"} <= names
    assert len(names) == 50
