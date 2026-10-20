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
