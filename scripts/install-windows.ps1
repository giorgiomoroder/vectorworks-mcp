# vectorworks-mcp installer for Windows. UNTESTED: this script, the uvx route and the Claude
# Desktop config were not run live. The MCP Listen trigger itself was live-tested on Vectorworks
# 2027 (German) with a checkout install (uv run vwmcp install-plugin --vw-version 2027) and
# Claude Code registered via:
#   claude mcp add -s user vectorworks -e VWMCP_VW_VERSION=2027 -- uv run --directory <checkout> vwmcp
#   powershell -ExecutionPolicy Bypass -File install-windows.ps1
#   powershell -ExecutionPolicy Bypass -File install-windows.ps1 -VwVersion 2027
# On Windows there is no automatic trigger: open the MCP Listen command in
# Vectorworks before asking Claude, and it runs the queued requests.
param(
  [string]$VwVersion = "2026",
  [string]$Source = "git+https://github.com/giorgiomoroder/vectorworks-mcp"
)
$ErrorActionPreference = "Stop"

if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
  Write-Host "Installing uv from astral.sh ..."
  powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
$uvx = (Get-Command uvx).Source

uvx --refresh --from $Source vwmcp install-plugin --vw-version $VwVersion

$cfg = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
if (Test-Path (Split-Path $cfg)) {
  if (Test-Path $cfg) { Copy-Item $cfg "$cfg.bak-vwmcp" }
  $json = if ((Test-Path $cfg) -and (Get-Content $cfg -Raw).Trim()) { Get-Content $cfg -Raw | ConvertFrom-Json } else { [pscustomobject]@{} }
  if (-not $json.mcpServers) { $json | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) }
  $entry = [pscustomobject]@{ command = $uvx; args = @("--from", $Source, "vwmcp"); env = [pscustomobject]@{ VWMCP_VW_VERSION = $VwVersion } }
  $json.mcpServers | Add-Member -NotePropertyName vectorworks -NotePropertyValue $entry -Force
  $json | ConvertTo-Json -Depth 10 | Set-Content $cfg -Encoding UTF8
  Write-Host "Added 'vectorworks' to $cfg"
}

Write-Host "`nInstalled 'MCP Run Job' and 'MCP Listen' (.vsm) next to the bridge."
Write-Host "Add MCP Listen to a menu once (MCP Run Job is an optional manual fallback). Standard workspaces are read-only: duplicate one first."
Write-Host "Before asking Claude, open MCP Listen in Vectorworks; press Stop to edit yourself."
Write-Host "Claude Code users register the server with (not run by this script):"
Write-Host "  claude mcp add -s user vectorworks -e VWMCP_VW_VERSION=$VwVersion -- uv run --directory <path-to-checkout> vwmcp"
