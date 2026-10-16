param(
    [string]$Workspace = '',
    [string]$FreeCADCmd = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Workspace) { $Workspace = Join-Path $projectRoot 'models' }
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & py -3.13 -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 could not create the virtual environment.' }
}
& $pythonPath -m pip install -e "${projectRoot}[dev]"
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
$setupArgs = @('-m', 'codex_freecad.setup', '--workspace', $Workspace, '--output', (Join-Path $projectRoot '.local'))
if ($FreeCADCmd) { $setupArgs += @('--freecad-cmd', $FreeCADCmd) }
& $pythonPath @setupArgs
if ($LASTEXITCODE -ne 0) { throw 'Configuration generation failed.' }
