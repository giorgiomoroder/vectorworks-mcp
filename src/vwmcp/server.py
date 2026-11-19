"""Entry point: `vwmcp` runs the MCP server (stdio); `vwmcp install-plugin`
installs the in-app bridge; `vwmcp doctor` checks the install."""

from __future__ import annotations

import argparse

from vwmcp import config, install
from vwmcp.app import mcp
from vwmcp.tools import drawing, generic, spotlight  # noqa: F401  (registers tools)


def main() -> None:
    parser = argparse.ArgumentParser(prog="vwmcp", description=__doc__)
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("install-plugin", help="copy the bridge into Vectorworks' Plug-ins folder")
    p.add_argument("--vw-version", default=config.VW_VERSION, help="Vectorworks user folder (default: $VWMCP_VW_VERSION or 2026)")
    p.add_argument("--target", help="explicit folder (default: user Plug-ins/vwmcp)")
    p.add_argument("--home", help="job folder this bridge serves (the server's VWMCP_HOME); default ~/.vwmcp")
    d = sub.add_parser("doctor", help="check bridge, Claude configs, Vectorworks process, runtime folder")
    d.add_argument("--vw-version", default=config.VW_VERSION)
    d.add_argument("--fix", action="store_true", help="remove stale job/result files")
    args = parser.parse_args()

    if args.cmd == "doctor":
        from vwmcp import doctor

        checks = doctor.run_checks(vw_version=args.vw_version, fix=args.fix)
        print(doctor.format_report(checks))
        raise SystemExit(0 if all(c.ok is not False for c in checks) else 1)

    if args.cmd == "install-plugin":
        from pathlib import Path

        target = Path(args.target) if args.target else install.plugin_dir(args.vw_version)
        print(install.install_plugin(target, home=args.home))
        return
    mcp.run("stdio")


if __name__ == "__main__":
    main()
