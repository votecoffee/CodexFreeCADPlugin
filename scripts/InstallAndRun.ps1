<#
.SYNOPSIS
Install the checkout and run a FreeCAD MCP server over stdio.
.DESCRIPTION
Uses Setup.ps1 to create/update the local virtual environment and generate macros
and configuration. Installation messages go to stderr to preserve MCP stdout.
FreeCAD and Python 3.13 must already be installed. No GUI is opened automatically.
.PARAMETER Mode
Run the headless backend (default), or connect to an existing live bridge.
.PARAMETER Workspace
CAD workspace. Relative paths resolve against the checkout; defaults to models.
.PARAMETER FreeCADCmd
Optional FreeCADCmd executable for setup and the headless backend.
.PARAMETER InstallOnly
Install dependencies and generate configuration, then exit.
.PARAMETER SkipInstall
Run with the existing virtual environment without installing or regenerating files.
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
    [switch]$InstallOnly,
    [switch]$SkipInstall,
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
  -InstallOnly         Install and generate configuration, then exit
  -SkipInstall         Start the existing installation without setup
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
    $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not $SkipInstall) {
        $setupArgs = @{ Workspace = $Workspace; FreeCADCmd = $FreeCADCmd }
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
