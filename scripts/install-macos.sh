#!/bin/bash
# vectorworks-mcp installer for macOS.
#   curl -LsSf https://raw.githubusercontent.com/giorgiomoroder/vectorworks-mcp/main/scripts/install-macos.sh | bash
# Options (environment variables):
#   VW_VERSION=2026          Vectorworks version to install for (default: newest installed)
#   VWMCP_SOURCE=<spec>      where to get the server (default: GitHub main)
#   SERVER_NAME=<name>       Claude server name (default: vectorworks, or
#                            vectorworks-<version> for a non-2026 version)
#   VWMCP_HOME=<folder>      job folder (default: ~/.vwmcp, or ~/.vwmcp-<version>)
# Run it once per Vectorworks version to use several side by side, e.g.
#   VW_VERSION=2027 bash install-macos.sh
set -euo pipefail

if [ -z "${VW_VERSION:-}" ]; then
  # newest installed Vectorworks, else 2026
  VW_VERSION="$(ls -d /Applications/Vectorworks\ 20[0-9][0-9] 2>/dev/null | sed 's/.* //' | sort | tail -1)"
  VW_VERSION="${VW_VERSION:-2026}"
fi
SOURCE="${VWMCP_SOURCE:-git+https://github.com/giorgiomoroder/vectorworks-mcp}"
if [ "$VW_VERSION" = "2026" ]; then
  SERVER_NAME="${SERVER_NAME:-vectorworks}"
  HOME_DIR="${VWMCP_HOME:-$HOME/.vwmcp}"
else
  SERVER_NAME="${SERVER_NAME:-vectorworks-$VW_VERSION}"
  HOME_DIR="${VWMCP_HOME:-$HOME/.vwmcp-$VW_VERSION}"
fi
ENV_JSON="{\"VWMCP_VW_VERSION\": \"$VW_VERSION\", \"VWMCP_HOME\": \"$HOME_DIR\"}"
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
"$UVX" --refresh --from "$SOURCE" vwmcp install-plugin --vw-version "$VW_VERSION" --home "$HOME_DIR"

say "3/4  Registering with Claude Desktop"
CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
if [ -d "$(dirname "$CFG")" ]; then
  [ -f "$CFG" ] && cp "$CFG" "$CFG.bak-vwmcp"
  "$UVX" python - "$CFG" "$UVX" "$SOURCE" "$SERVER_NAME" "$ENV_JSON" <<'PY'
import json, sys, pathlib
path, uvx, source, name, env = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], json.loads(sys.argv[5])
cfg = json.loads(path.read_text()) if path.exists() and path.read_text().strip() else {}
cfg.setdefault("mcpServers", {})[name] = {"command": uvx, "args": ["--from", source, "vwmcp"], "env": env}
path.write_text(json.dumps(cfg, indent=2) + "\n")
print(f"Added '{name}' to {path}")
PY
else
  echo "Claude Desktop not found; skipping. (See docs/claude-config.md)"
fi

say "4/4  Registering with Claude Code"
if command -v claude >/dev/null 2>&1; then
  claude mcp remove --scope user "$SERVER_NAME" >/dev/null 2>&1 || true
  claude mcp add --scope user "$SERVER_NAME" -e "VWMCP_VW_VERSION=$VW_VERSION" -e "VWMCP_HOME=$HOME_DIR" -- "$UVX" --from "$SOURCE" vwmcp
else
  echo "Claude Code not found; skipping."
fi

cat <<'MSG'

Almost done. One-time step inside Vectorworks (about 1 minute).
The "MCP Run Job" command file is installed; Vectorworks loads it at
startup, so quit and reopen Vectorworks if it was running just now. Then:

  Tools > Workspaces > Edit Current Workspace... > Menus tab:
  drag "MCP Run Job" (under Miscellaneous) into any menu, e.g. Tools.

Then quit and reopen Claude Desktop. The first time Claude talks to
Vectorworks, macOS asks to allow control of Vectorworks: click Allow.
MSG
