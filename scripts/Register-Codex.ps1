param([string]$Workspace = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Workspace) { $Workspace = Join-Path $projectRoot 'models' }
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts\Setup.ps1 first.' }
foreach ($mode in @('live', 'headless')) {
    & codex mcp add "freecad-$mode" -- $pythonPath -m codex_freecad.server --mode $mode --workspace $Workspace
    if ($LASTEXITCODE -ne 0) { throw "Could not register freecad-$mode." }
}
Write-Output 'Both FreeCAD MCP servers registered. Start a new Codex chat to load them.'
