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
    $appRoot = Join-Path $env:LOCALAPPDATA 'FreeCADMCPServer'
    $pointerPath = Join-Path $appRoot 'launcher\current.json'
    if (-not (Test-Path -LiteralPath $pointerPath)) { throw 'Run Install.cmd to prepare the stable installation first.' }
    $pointer = Get-Content -LiteralPath $pointerPath -Raw | ConvertFrom-Json
    if ($pointer.snapshot -notmatch '^[a-f0-9]{64}$') { throw 'Invalid selected snapshot.' }
    $selectedBytes = [IO.File]::ReadAllBytes((Join-Path $appRoot "launcher\snapshots\$($pointer.snapshot)\manifest.json"))
    $selectedHasher = [Security.Cryptography.SHA256]::Create()
    try { $selectedDigest = [BitConverter]::ToString($selectedHasher.ComputeHash($selectedBytes)).Replace('-','').ToLowerInvariant() }
    finally { $selectedHasher.Dispose() }
    if ($selectedDigest -ne $pointer.snapshot) { throw 'Selected snapshot changed.' }
    $selected = [Text.Encoding]::UTF8.GetString($selectedBytes) | ConvertFrom-Json
    $Output = Split-Path -Parent (Join-Path $appRoot $selected.entry)
}
$oldPythonPath = $env:PYTHONPATH
$oldBytecode = $env:PYTHONDONTWRITEBYTECODE
try {
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$integrationArgs = @('-m', 'codex_freecad.integration', '--output', $Output, '--integration', $Integration)
if ($CodexHome) { $integrationArgs += @('--codex-home', $CodexHome) }
if (-not $Preview) { $integrationArgs += '--apply' }
& $pythonPath @integrationArgs
if ($LASTEXITCODE -ne 0) { throw 'Codex integration failed. Existing connections were preserved.' }
if (-not $Preview -and $Integration -eq 'standalone') {
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
    $release = Get-Content -LiteralPath (Join-Path $Output 'plugin\release.json') -Raw | ConvertFrom-Json
    $canonical = & $pythonPath -m codex_freecad.versioning "--canonical=$($plugin[0].version)"
    if ($LASTEXITCODE -ne 0 -or $canonical -ne $release.package_version) {
        throw 'Installed FreeCAD plugin version differs from the prepared release.'
    }
    $record = @{plugin_id = $plugin[0].pluginId; version = $canonical; display_version = $release.display_version}
    $pluginRoute = (Get-Content -LiteralPath (Join-Path $Output 'plugin\.mcp.json') -Raw | ConvertFrom-Json).mcpServers.freecad
    $managedRoot = Split-Path -Parent $pluginRoute.args[3]
    $metadataPath = Join-Path $managedRoot 'installed-plugin.json'
    $metadataPending = $metadataPath + '.' + [Guid]::NewGuid().ToString('N') + '.pending'
    [IO.File]::WriteAllText($metadataPending, ($record | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $metadataPath) {
        [IO.File]::Replace($metadataPending, $metadataPath, ($metadataPath + '.' + [Guid]::NewGuid().ToString('N') + '.previous'))
    }
    else { [IO.File]::Move($metadataPending, $metadataPath) }
}
} finally { $env:PYTHONPATH = $oldPythonPath; $env:PYTHONDONTWRITEBYTECODE = $oldBytecode }
