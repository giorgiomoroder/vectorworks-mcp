`MCP Run Job.vsm` is the Vectorworks menu command that runs the bridge
(`from vwmcp import vwmcp_bridge; vwmcp_bridge.run_pending()`). Vectorworks
can only create such files in its Plug-in Manager, but a copy works in any
user Plug-ins folder (checked on 2026 and 2027), so `vwmcp install-plugin`
installs this one next to the bridge and nobody has to create it by hand.
Only the drag into a menu (Tools > Workspaces > Edit Current Workspace)
stays manual. Made on Vectorworks 2026 (English) by giorgiomoroder.

`MCP Listen.vsm` is the Windows-only counterpart (category Scripts; script
`from vwmcp import vwmcp_bridge; vwmcp_bridge.listen()`). It opens a small
window that runs Claude's requests automatically while it is open, because
Windows has no automatic trigger. `vwmcp install-plugin` places it next to
the other file on Windows only. Made on Vectorworks 2027 (German) on Windows.
