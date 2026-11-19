# Claude configuration

The installer does this for you. To do it by hand:

## Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(Windows: `%APPDATA%\Claude\claude_desktop_config.json`) and add a
`vectorworks` entry under `mcpServers`:

```json
{
  "mcpServers": {
    "vectorworks": {
      "command": "/opt/homebrew/bin/uvx",
      "args": ["--from", "git+https://github.com/giorgiomoroder/vectorworks-mcp", "vwmcp"]
    }
  }
}
```

Use the full path to `uvx` (`which uvx` in Terminal); Claude Desktop doesn't
see your shell's PATH. Common locations: `/opt/homebrew/bin/uvx` (Homebrew),
`~/.local/bin/uvx` (uv installer; write it out as `/Users/<you>/.local/bin/uvx`).
Restart Claude Desktop afterwards.

## Claude Code

```bash
claude mcp add --scope user vectorworks -- uvx --from git+https://github.com/giorgiomoroder/vectorworks-mcp vwmcp
```

Or in a project's `.mcp.json`:

```json
{
  "mcpServers": {
    "vectorworks": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/giorgiomoroder/vectorworks-mcp", "vwmcp"]
    }
  }
}
```

## From a local checkout

Replace the `uvx` command with:

```json
"command": "uv",
"args": ["run", "--project", "/path/to/vectorworks-mcp", "vwmcp"]
```

## Environment variables

Set these in the server's `env` block if you need them:

| Variable | Default | Meaning |
|---|---|---|
| `VWMCP_VW_VERSION` | `2026` | Vectorworks version: app name, user Plug-ins and Libraries folders |
| `VWMCP_APP` | `Vectorworks <version>` | Application name AppleScript talks to (override only if yours is renamed) |
| `VWMCP_HOME` | `~/.vwmcp` | Job, result, journal and log folder |
| `VWMCP_TIMEOUT` | `30` | Seconds to wait for Vectorworks per request |
| `VWMCP_MIN_UPTIME` | `30` | Seconds after launch before Claude may send requests |

The bridge in Vectorworks reads `vwmcp_home.txt` next to itself to know
which folder's jobs to run (written by `vwmcp install-plugin --home ...`);
without that file it uses `~/.vwmcp`. The menu command stays the same.

## Two Vectorworks versions side by side

One server process serves one Vectorworks. To keep using 2026 while trying
2027, register a second server with its own version and folder:

```bash
VW_VERSION=2027 bash scripts/install-macos.sh
```

That installs the bridge into the 2027 user Plug-ins folder (pointing at
`~/.vwmcp-2027`) and adds a `vectorworks-2027` server to Claude Desktop and
Claude Code with `VWMCP_VW_VERSION=2027` and `VWMCP_HOME=~/.vwmcp-2027`.
Create the "MCP Run Job" menu command in the 2027 workspace too (or let
Vectorworks' migration copy it: it lives in the user Plug-ins folder as
`MCP Run Job.vsm`). Each app only ever runs its own server's jobs, and each
server has its own journal, so `vw_revert_last` can't cross over. In Claude,
tools appear twice, prefixed by server name; say which version you mean.
`vwmcp doctor` checks one server at a time: run it with that server's
environment (`VWMCP_VW_VERSION=2027 VWMCP_HOME=~/.vwmcp-2027 vwmcp doctor`).
