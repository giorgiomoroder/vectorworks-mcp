#!/bin/bash
# vectorworks-mcp installer for macOS.
#   curl -LsSf https://raw.githubusercontent.com/giorgiomoroder/vectorworks-mcp/main/scripts/install-macos.sh | bash
# Options (environment variables):
#   VW_VERSION=2026          Vectorworks version folder to install into
#   VWMCP_SOURCE=<spec>      where to get the server (default: GitHub main)
set -euo pipefail

VW_VERSION="${VW_VERSION:-2026}"
SOURCE="${VWMCP_SOURCE:-git+https://github.com/giorgiomoroder/vectorworks-mcp}"
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

say "1/4  Checking for uv (Python package runner)"
if command -v uvx >/dev/null 2>&1; then
  UVX="$(command -v uvx)"
elif [ -x "$HOME/.local/bin/uvx" ]; then
  UVX="$HOME/.local/bin/uvx"
else
  echo "Installing uv from astral.sh ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  UVX="$HOME/.local/bin/uvx"
fi
echo "Using $UVX"

say "2/4  Installing the Vectorworks bridge into your Plug-ins folder"
"$UVX" --refresh --from "$SOURCE" vwmcp install-plugin --vw-version "$VW_VERSION"

say "3/4  Registering with Claude Desktop"
CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
if [ -d "$(dirname "$CFG")" ]; then
  [ -f "$CFG" ] && cp "$CFG" "$CFG.bak-vwmcp"
  "$UVX" python - "$CFG" "$UVX" "$SOURCE" <<'PY'
import json, sys, pathlib
path, uvx, source = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
cfg = json.loads(path.read_text()) if path.exists() and path.read_text().strip() else {}
cfg.setdefault("mcpServers", {})["vectorworks"] = {"command": uvx, "args": ["--from", source, "vwmcp"]}
path.write_text(json.dumps(cfg, indent=2) + "\n")
print(f"Added 'vectorworks' to {path}")
PY
else
  echo "Claude Desktop not found; skipping. (See docs/claude-config.md)"
fi

say "4/4  Registering with Claude Code"
if command -v claude >/dev/null 2>&1; then
  claude mcp remove --scope user vectorworks >/dev/null 2>&1 || true
  claude mcp add --scope user vectorworks -- "$UVX" --from "$SOURCE" vwmcp
else
  echo "Claude Code not found; skipping."
fi

cat <<'MSG'

Almost done. One-time step inside Vectorworks (about 2 minutes):

  1. Tools > Plug-ins > Plug-in Manager...  > Custom Plug-ins > New...
     Type: Command   Name: MCP Run Job
  2. Select it > Edit Script...  > Language: Python, paste these two lines:

         from vwmcp import vwmcp_bridge
         vwmcp_bridge.run_pending()

  3. Tools > Workspaces > Edit Current Workspace... > Menus tab:
     drag "MCP Run Job" (under Miscellaneous) into any menu, e.g. Tools.

Then quit and reopen Claude Desktop. The first time Claude talks to
Vectorworks, macOS asks to allow control of Vectorworks: click Allow.
MSG
