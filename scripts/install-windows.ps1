# vectorworks-mcp installer for Windows (EXPERIMENTAL: untested in v0.1).
#   powershell -ExecutionPolicy Bypass -File install-windows.ps1
# On Windows there is no automatic trigger yet: run Tools > MCP Run Job
# in Vectorworks to process each queued request.
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
  $entry = [pscustomobject]@{ command = $uvx; args = @("--from", $Source, "vwmcp") }
  $json.mcpServers | Add-Member -NotePropertyName vectorworks -NotePropertyValue $entry -Force
  $json | ConvertTo-Json -Depth 10 | Set-Content $cfg -Encoding UTF8
  Write-Host "Added 'vectorworks' to $cfg"
}

Write-Host "`nNow create the 'MCP Run Job' menu command in Vectorworks (see README)."
