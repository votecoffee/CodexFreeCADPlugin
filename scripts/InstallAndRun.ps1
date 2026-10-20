<#
.SYNOPSIS
Install the checkout and run a FreeCAD MCP server over stdio.
.DESCRIPTION
Uses Setup.ps1 to create/update the local virtual environment, generate configuration
and install FreeCAD's own Codex plugin. Installation messages go to stderr to preserve MCP stdout.
FreeCAD and Python 3.13 must already be installed. No GUI is opened automatically.
.PARAMETER Mode
Run the headless backend (default), or connect to an existing live bridge.
.PARAMETER Workspace
CAD workspace. Relative paths resolve against the checkout; defaults to models.
.PARAMETER FreeCADCmd
Optional FreeCADCmd executable for setup and the headless backend.
.PARAMETER InstallOnly
Install dependencies, generate configuration and install the Codex plugin, then exit.
.PARAMETER Integration
Codex integration: standalone (default), or none for configuration only.
.PARAMETER SkipInstall
Run with the existing virtual environment without installing or regenerating files.
.PARAMETER NoStartMenuShortcut
Install without creating or updating the current user's Start menu shortcut.
.PARAMETER Help
Print launcher usage without installing or starting anything.
.EXAMPLE
Install-and-Run.cmd
.EXAMPLE
Install-and-Run.cmd -Mode live -SkipInstall
#>
[CmdletBinding()]
param(
    [ValidateSet('headless', 'live')]
    [string]$Mode = 'headless',
    [string]$Workspace = '',
    [string]$FreeCADCmd = '',
    [ValidateSet('standalone', 'none')]
    [string]$Integration = 'standalone',
    [switch]$InstallOnly,
    [switch]$SkipInstall,
    [switch]$NoStartMenuShortcut,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
try {
    if ($Help) {
        [Console]::Error.WriteLine(@'
Usage: Install-and-Run.cmd [options]
  -Mode headless|live   Backend to run (default: headless)
  -Workspace PATH      CAD workspace (default: models in this checkout)
  -FreeCADCmd PATH     Optional FreeCADCmd executable
  -Integration ROUTE   standalone (default), or none
  -InstallOnly         Install, including the Codex plugin, then exit
  -SkipInstall         Start the existing installation without setup
  -NoStartMenuShortcut  Skip Start menu shortcut creation during setup
  -Help                Show this help
The server speaks MCP over stdio and waits for a client. Start the live bridge manually.
'@)
        exit 0
    }
    if ($InstallOnly -and $SkipInstall) {
        throw 'Use either -InstallOnly or -SkipInstall.'
    }
    $projectRoot = Split-Path -Parent $PSScriptRoot
    if (-not $Workspace) { $Workspace = 'models' }
    if (-not [IO.Path]::IsPathRooted($Workspace)) {
        $Workspace = Join-Path $projectRoot $Workspace
    }
    $Workspace = [IO.Path]::GetFullPath($Workspace)
    if ($FreeCADCmd) {
        $FreeCADCmd = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($FreeCADCmd)
    }
    $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not $SkipInstall) {
        $setupArgs = @{
            Workspace = $Workspace; FreeCADCmd = $FreeCADCmd
            ShortcutMode = $Mode; NoStartMenuShortcut = [bool]$NoStartMenuShortcut
            Integration = $Integration
        }
        & (Join-Path $PSScriptRoot 'Setup.ps1') @setupArgs |
            ForEach-Object { [Console]::Error.WriteLine([string]$_) }
    }
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw 'Virtual environment missing. Run Install-and-Run.cmd without -SkipInstall.'
    }
    if ($InstallOnly) { exit 0 }
    $serverArgs = @('-m', 'codex_freecad.server', '--mode', $Mode, '--workspace', $Workspace)
    if ($Mode -eq 'headless' -and $FreeCADCmd) {
        $serverArgs += @('--freecad-cmd', $FreeCADCmd)
    }
    [Console]::Error.WriteLine("Starting FreeCADMCPServer ($Mode) over stdio; waiting for an MCP client.")
    if ($Mode -eq 'live') {
        [Console]::Error.WriteLine('In FreeCAD, execute the generated .local\StartBridge.FCMacro to connect this workspace.')
    }
    & $pythonPath @serverArgs
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine('FreeCADMCPServer: ' + $_.Exception.Message)
    exit 1
}
