"""Which Vectorworks this server instance talks to.

One server process serves one Vectorworks version. To use two versions side by
side (say 2026 and 2027), register two servers with different environments:

    VWMCP_VW_VERSION=2027  VWMCP_HOME=~/.vwmcp-2027

and install the bridge into that version's Plug-ins folder with the same home
(`vwmcp install-plugin --vw-version 2027 --home ~/.vwmcp-2027`), so jobs,
results, the journal and the log never mix between the two apps.
"""

from __future__ import annotations

import os

VW_VERSION = os.environ.get("VWMCP_VW_VERSION", "2026")
DEFAULT_APP = os.environ.get("VWMCP_APP", f"Vectorworks {VW_VERSION}")
