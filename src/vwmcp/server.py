"""Entry point: `vwmcp` runs the MCP server (stdio); `vwmcp install-plugin`
installs the in-app bridge; `vwmcp doctor` checks the install; `vwmcp lint
FILE...` checks scripts for Vectorworks; `vwmcp dump-api` refreshes the vs.*
signature table from a running Vectorworks."""

from __future__ import annotations

import argparse

from vwmcp import config, install
from vwmcp.app import mcp
from vwmcp.tools import drawing, generic, spotlight  # noqa: F401  (registers tools)

for _name in config.tools_off():
    mcp.remove_tool(_name)


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
    lp = sub.add_parser("lint", help="check Python files for Vectorworks (syntax, vs.* signatures)")
    lp.add_argument("files", nargs="+")
    dp = sub.add_parser("dump-api", help="write vs_api_<year>.json from the running Vectorworks' docstrings")
    dp.add_argument("--out", help="output file (default: vs_api_<year>.json in the current folder)")
    args = parser.parse_args()

    if args.cmd == "lint":
        from vwmcp import vslint

        bad = 0
        for f in args.files:
            with open(f, encoding="utf-8") as fh:
                report = vslint.lint(fh.read(), f, year=config.VW_VERSION)
            print(vslint.format_report(report, f) or f"{f}: ok")
            bad += len(report["errors"])
        raise SystemExit(1 if bad else 0)

    if args.cmd == "dump-api":
        import json
        from pathlib import Path

        from vwmcp import vslint

        ping = generic.vw_ping()
        res = generic._run_raw(vslint.DOCS_CODE, 120)
        if not res.get("ok"):
            raise SystemExit(f"Vectorworks did not return the docstrings: {res.get('error')}")
        table = vslint.build_table(res["value"], f"{config.VW_VERSION} ({ping['vectorworks_version']})")
        out = Path(args.out) if args.out else Path(f"vs_api_{config.VW_VERSION}.json")
        out.write_text(json.dumps(table, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"{out}: {len(table['signatures'])} signatures, {len(table['deprecated'])} deprecated, "
              f"{len(table['known_without_signature'])} without a definition")
        return

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
