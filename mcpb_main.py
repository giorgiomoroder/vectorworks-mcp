"""Entry point of the Claude Desktop extension bundle (.mcpb).

Claude Desktop runs it with `uv run --directory <bundle> mcpb_main.py`, which
installs this project and its one dependency (mcp) into a private environment
first. The server itself is `vwmcp.server.main` (stdio)."""

import sys

if sys.version_info < (3, 11):
    sys.exit(
        "vectorworks-mcp needs Python 3.11 or newer (this is %d.%d). Install uv "
        "(https://docs.astral.sh/uv/) or Python 3.11+ from python.org, then reinstall the "
        "extension." % sys.version_info[:2]
    )

from vwmcp.server import main  # noqa: E402

main()
