param(
    [string]$Workspace = '',
    [string]$FreeCADCmd = '',
    [string[]]$Extensions = @(),
    [ValidateSet('headless', 'live')]
    [string]$ShortcutMode = 'headless',
    [ValidateSet('standalone', 'none')]
    [string]$Integration = 'standalone',
    [switch]$NoStartMenuShortcut
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Workspace) { $Workspace = Join-Path $projectRoot 'models' }
$Workspace = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Workspace)
if ($FreeCADCmd) {
    $FreeCADCmd = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($FreeCADCmd)
}
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & py -3.13 -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 could not create the virtual environment.' }
}
# Validate the explicit selection before regenerating any installation files.
if (Test-Path -LiteralPath (Join-Path $projectRoot '.local\framework-installation.json')) {
    $selectionJson = & $pythonPath -m codex_freecad.installed_host --output (Join-Path $projectRoot '.local')
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read the selected FreeCAD installation.' }
    $selection = $selectionJson | ConvertFrom-Json
    if ($Workspace -ne $selection.workspace -or $Extensions.Count -gt 0 -or $FreeCADCmd) {
        throw 'Selected framework publication owns its workspace and extensions. Update it explicitly before changing setup options.'
    }
}
& $pythonPath -m pip install -e "${projectRoot}[dev]"
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
$setupArgs = @('-m', 'codex_freecad.setup', '--workspace', $Workspace, '--output', (Join-Path $projectRoot '.local'))
if ($FreeCADCmd) { $setupArgs += @('--freecad-cmd', $FreeCADCmd) }
foreach ($directory in $Extensions) { $setupArgs += @('--extensions', $directory) }
& $pythonPath @setupArgs
if ($LASTEXITCODE -ne 0) { throw 'Configuration generation failed.' }
if ($Integration -ne 'none') {
    & (Join-Path $PSScriptRoot 'Install-CodexPlugin.ps1') -Integration $Integration
}
if (-not $NoStartMenuShortcut) {
    & (Join-Path $PSScriptRoot 'Create-StartMenuShortcut.ps1') -Workspace $Workspace -FreeCADCmd $FreeCADCmd -Mode $ShortcutMode
}
