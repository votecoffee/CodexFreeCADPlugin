param(
    [string]$Workspace = '',
    [string]$FreeCADCmd = '',
    [string]$FrameworkWheel = '',
    [string]$FrameworkSha256 = '',
    [string[]]$Extensions = @(),
    [ValidateSet('headless', 'live')]
    [string]$ShortcutMode = 'headless',
    [ValidateSet('standalone', 'none')]
    [string]$Integration = 'standalone',
    [switch]$NoStartMenuShortcut
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([bool]$FrameworkWheel -ne [bool]$FrameworkSha256) { throw 'Supply both -FrameworkWheel and -FrameworkSha256.' }
if ($FrameworkWheel) {
    $FrameworkWheel = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($FrameworkWheel)
    $wheelStream = [IO.File]::OpenRead($FrameworkWheel)
    $wheelHasher = [Security.Cryptography.SHA256]::Create()
    try { $wheelDigest = [BitConverter]::ToString($wheelHasher.ComputeHash($wheelStream)).Replace('-', '') }
    finally { $wheelHasher.Dispose(); $wheelStream.Dispose() }
    if ($FrameworkSha256 -notmatch '^[a-fA-F0-9]{64}$' -or $wheelDigest -ne $FrameworkSha256) {
        throw 'Framework wheel does not match the supplied trusted SHA-256.'
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $wheelArchive = [IO.Compression.ZipFile]::OpenRead($FrameworkWheel)
    try {
        $metadataEntry = @($wheelArchive.Entries | Where-Object { $_.FullName -eq 'universal_codex_tools-0.20.0.dist-info/METADATA' })
        if ($metadataEntry.Count -ne 1) { throw 'Expected the reviewed universal-codex-tools 0.20.0 wheel.' }
        $reader = New-Object IO.StreamReader($metadataEntry[0].Open())
        try { $metadata = $reader.ReadToEnd().Replace("`r`n", "`n") } finally { $reader.Dispose() }
        if ($metadata -notmatch '(?m)^Name: universal-codex-tools$' -or $metadata -notmatch '(?m)^Version: 0\.20\.0$') {
            throw 'Unexpected framework distribution or version.'
        }
    } finally { $wheelArchive.Dispose() }
}
if (-not $Workspace) { $Workspace = Join-Path $projectRoot 'models' }
$Workspace = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Workspace)
if ($FreeCADCmd) {
    $FreeCADCmd = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($FreeCADCmd)
}
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    if (-not $FrameworkWheel) { throw 'A fresh setup requires -FrameworkWheel and its trusted -FrameworkSha256 for framework 0.20.0.' }
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
if ($FrameworkWheel) {
    & $pythonPath -m pip install --no-deps $FrameworkWheel
    if ($LASTEXITCODE -ne 0) { throw 'Reviewed framework wheel installation failed.' }
}
$frameworkVersion = & $pythonPath -c "import importlib.metadata as m; print(next((d.version for d in m.distributions() if d.metadata.get('Name', '').lower().replace('_', '-') == 'universal-codex-tools'), ''))"
if ($LASTEXITCODE -ne 0 -or $frameworkVersion -ne '0.20.0') { throw 'Framework 0.20.0 is required. Supply -FrameworkWheel and its trusted -FrameworkSha256.' }
& $pythonPath -m pip install -e "${projectRoot}[dev,managed]"
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
