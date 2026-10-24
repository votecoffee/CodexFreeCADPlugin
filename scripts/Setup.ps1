param(
    [string]$Workspace = '',
    [string]$FreeCADCmd = '',
    [string]$FrameworkWheel = '',
    [string]$FrameworkSha256 = '',
    [string]$InstallRoot = '',
    [string]$Wheelhouse = '',
    [string]$BridgeDescriptor = '',
    [string[]]$Extensions = @(),
    [ValidateSet('', 'headless', 'live')]
    [string]$ShortcutMode = '',
    [ValidateSet('standalone', 'none')]
    [string]$Integration = 'standalone',
    [switch]$NoStartMenuShortcut
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
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
if ($Extensions.Count -gt 0) { throw 'The stable profile uses reviewed bundled extensions. Prepare explicit immutable extension updates separately.' }
if (-not $InstallRoot) { $InstallRoot = Join-Path $env:USERPROFILE '.local\share\FreeCADMCPServer' }
$InstallRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($InstallRoot)
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & py -3.13 -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 could not create the virtual environment.' }
}
$buildArgs = @('-B', (Join-Path $PSScriptRoot 'install_stable.py'), '--project', $projectRoot, '--root', $InstallRoot)
if ($Workspace) { $buildArgs += @('--workspace', [IO.Path]::GetFullPath($Workspace)) }
if ($ShortcutMode) { $buildArgs += @('--mode', $ShortcutMode) }
if ($FrameworkWheel) { $buildArgs += @('--framework-wheel', $FrameworkWheel) }
if ($Wheelhouse) { $buildArgs += @('--wheelhouse', [IO.Path]::GetFullPath($Wheelhouse)) }
if ($BridgeDescriptor -and $FreeCADCmd) { throw 'Select one explicit native target.' }
if ($BridgeDescriptor -and $ShortcutMode -and $ShortcutMode -ne 'live') { throw 'A bridge descriptor requires live mode.' }
if ($FreeCADCmd -and $ShortcutMode -eq 'live') { throw 'Use -BridgeDescriptor for live mode.' }
if ($BridgeDescriptor) { $buildArgs += @('--native-target', [IO.Path]::GetFullPath($BridgeDescriptor), '--mode', 'live') }
elseif ($FreeCADCmd) { $buildArgs += @('--native-target', [IO.Path]::GetFullPath($FreeCADCmd)) }
$installedJson = (& $pythonPath @buildArgs) -join [Environment]::NewLine
if ($LASTEXITCODE -ne 0) { throw 'Stable runtime preparation/selection failed; retained profiles were preserved.' }
$installed = ConvertFrom-Json -InputObject $installedJson
$InstallRoot = $installed.installation_root
$iconFolder = Join-Path $InstallRoot 'assets'
[void][IO.Directory]::CreateDirectory($iconFolder)
Copy-Item -LiteralPath (Join-Path $projectRoot 'assets\FreeCADMCPServer.ico') -Destination (Join-Path $iconFolder 'FreeCADMCPServer.ico') -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Show-InstalledStatus.ps1') -Destination (Join-Path $InstallRoot 'Show-Status.ps1') -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'inspect_stable.py') -Destination (Join-Path $InstallRoot 'Inspect-Selection.py') -Force
if ($Integration -ne 'none') {
    & (Join-Path $PSScriptRoot 'Install-CodexPlugin.ps1') -Integration $Integration -Output (Split-Path -Parent $installed.plugin)
}
if (-not $NoStartMenuShortcut) {
    & (Join-Path $PSScriptRoot 'Create-StartMenuShortcut.ps1') -InstallRoot $InstallRoot
}
Write-Output $installedJson
