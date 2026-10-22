<#
.SYNOPSIS
Install FreeCAD's standalone Codex plugin.
.DESCRIPTION
Run setup first with -Integration none when preparing a preview. Preview prints a plan
without changing Codex. Existing direct integrations are never removed automatically.
#>
param(
    [ValidateSet('standalone', 'none')]
    [string]$Integration = 'standalone',
    [string]$CodexHome = '',
    [string]$Output = '',
    [switch]$Preview
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw 'Run scripts\Setup.ps1 first.' }
if (-not $Output) {
    $localOutput = Join-Path $projectRoot '.local'
    $selectionJson = & $pythonPath -m codex_freecad.installed_host --output $localOutput
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read the selected FreeCAD installation.' }
    $selection = $selectionJson | ConvertFrom-Json
    $Output = if ($null -ne $selection) { $selection.output } else { $localOutput }
}
$integrationArgs = @('-m', 'codex_freecad.integration', '--output', $Output, '--integration', $Integration)
if ($CodexHome) { $integrationArgs += @('--codex-home', $CodexHome) }
if (-not $Preview) { $integrationArgs += '--apply' }
& $pythonPath @integrationArgs
if ($LASTEXITCODE -ne 0) { throw 'Codex integration failed. Existing connections were preserved.' }
if (-not $Preview -and $Integration -eq 'standalone' -and (Test-Path -LiteralPath (Join-Path $Output 'application.json'))) {
    $previousCodexHome = $env:CODEX_HOME
    try {
        if ($CodexHome) { $env:CODEX_HOME = $CodexHome }
        $inventoryJson = & codex plugin list --json
        if ($LASTEXITCODE -ne 0) { throw 'Cannot read installed FreeCAD plugin version.' }
    } finally {
        $env:CODEX_HOME = $previousCodexHome
    }
    $plugin = @(($inventoryJson | ConvertFrom-Json).installed | Where-Object { $_.pluginId -eq 'freecad-modeling@freecad-development' -and $_.installed })
    if ($plugin.Count -ne 1) { throw 'FreeCAD plugin identity is missing or ambiguous.' }
    $record = @{plugin_id = $plugin[0].pluginId; version = $plugin[0].version}
    $metadataPath = Join-Path $Output 'installed-plugin.json'
    $metadataPending = $metadataPath + '.' + [Guid]::NewGuid().ToString('N') + '.pending'
    [IO.File]::WriteAllText($metadataPending, ($record | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $metadataPath) {
        [IO.File]::Replace($metadataPending, $metadataPath, ($metadataPath + '.' + [Guid]::NewGuid().ToString('N') + '.previous'))
    }
    else { [IO.File]::Move($metadataPending, $metadataPath) }
}
