<#
.SYNOPSIS
Install/select a retained standalone runtime, or run the app-owned stable entry.
#>
[CmdletBinding()]
param(
    [ValidateSet('', 'headless', 'live')][string]$Mode = '',
    [string]$Workspace = '', [string]$FreeCADCmd = '',
    [string]$FrameworkWheel = '', [string]$FrameworkSha256 = '',
    [string]$InstallRoot = '', [string]$Wheelhouse = '', [string]$BridgeDescriptor = '',
    [ValidateSet('standalone', 'none')][string]$Integration = 'standalone',
    [switch]$InstallOnly, [switch]$SkipInstall, [switch]$NoStartMenuShortcut, [switch]$Help
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
try {
    if ($Help) {
        [Console]::Error.WriteLine(@'
Usage: Install-and-Run.cmd [options]
  -InstallOnly          Install/select the stable runtime and standalone plugin
  -SkipInstall          Run the existing stable selection without building/installing
  -InstallRoot PATH     App-owned root (default: USERPROFILE\.local\share\FreeCADMCPServer)
  -Workspace PATH       Explicit CAD workspace; otherwise preserve the installed one
  -Mode headless|live   Preserve installed mode unless explicitly selected
  -FreeCADCmd PATH      Explicit headless executable (hashed, never run by installation)
  -BridgeDescriptor PATH  Explicit existing live bridge; no GUI starts
  -Wheelhouse PATH      Reuse reviewed wheels without downloading
  -FrameworkWheel PATH  Reviewed framework 0.20.0 wheel for a fresh installation
  -FrameworkSha256 HASH  Trusted wheel hash (must also match the reviewed runtime lock)
  -Integration standalone|none  Install own plugin, or prepare selection only
  -NoStartMenuShortcut  Skip the installed-status shortcut
  -Help                Show help without installation or native execution
Normal MCP connections launch the retained pythonw entry directly. No checkout/cache is needed.
'@)
        exit 0
    }
    if ($InstallOnly -and $SkipInstall) { throw 'Use either -InstallOnly or -SkipInstall.' }
    if ($SkipInstall -and ($FrameworkWheel -or $FrameworkSha256 -or $Wheelhouse)) { throw 'Wheel options require installation; omit -SkipInstall.' }
    $projectRoot = Split-Path -Parent $PSScriptRoot
    if (-not $InstallRoot) { $InstallRoot = Join-Path $env:USERPROFILE '.local\share\FreeCADMCPServer' }
    $InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
    if ($Workspace -and -not [IO.Path]::IsPathRooted($Workspace)) { $Workspace = Join-Path $projectRoot $Workspace }
    if (-not $SkipInstall) {
        $setupArgs = @{Workspace=$Workspace; FreeCADCmd=$FreeCADCmd; FrameworkWheel=$FrameworkWheel; FrameworkSha256=$FrameworkSha256;
            InstallRoot=$InstallRoot; Wheelhouse=$Wheelhouse; BridgeDescriptor=$BridgeDescriptor; ShortcutMode=$Mode;
            NoStartMenuShortcut=[bool]$NoStartMenuShortcut; Integration=$Integration}
        & (Join-Path $PSScriptRoot 'Setup.ps1') @setupArgs | ForEach-Object { [Console]::Error.WriteLine([string]$_) }
    }
    if ($InstallOnly) { exit 0 }
    $receiptPath = Join-Path $InstallRoot 'installation.json'
    if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) { throw 'Stable installation missing. Run Install.cmd first.' }
    $pointer = Get-Content -LiteralPath (Join-Path $InstallRoot 'launcher\current.json') -Raw | ConvertFrom-Json
    if ($pointer.snapshot -notmatch '^[a-f0-9]{64}$') { throw 'Invalid installed snapshot identity.' }
    $manifestBytes = [IO.File]::ReadAllBytes((Join-Path $InstallRoot "launcher\snapshots\$($pointer.snapshot)\manifest.json"))
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $manifestDigest = [BitConverter]::ToString($hasher.ComputeHash($manifestBytes)).Replace('-','').ToLowerInvariant() }
    finally { $hasher.Dispose() }
    if ($manifestDigest -ne $pointer.snapshot) { throw 'Selected manifest changed.' }
    $manifest = [Text.Encoding]::UTF8.GetString($manifestBytes) | ConvertFrom-Json
    $InstallRoot = $manifest.installation_root
    if ($Workspace -or $Mode -or $FreeCADCmd -or $BridgeDescriptor) { throw 'Run uses the exact installed selection. Change workspace/mode/target through Install.cmd.' }
    $route = $manifest.route
    $entry = Join-Path $InstallRoot 'Start-Mcp.py'
    if ($route.args.Count -ne 4 -or ($route.args[0..2] -join ' ') -ne '-I -S -B' -or $route.args[3] -ne $entry -or $route.cwd -ne (Join-Path $InstallRoot 'cwd') -or $route.command -ne $manifest.python -or [IO.Path]::GetFileName($route.command) -ne 'pythonw.exe') { throw 'Installed stable route differs from this root.' }
    $pythonStream = [IO.File]::OpenRead($route.command)
    $pythonHasher = [Security.Cryptography.SHA256]::Create()
    try { $pythonDigest = [BitConverter]::ToString($pythonHasher.ComputeHash($pythonStream)).Replace('-','').ToLowerInvariant() }
    finally { $pythonHasher.Dispose(); $pythonStream.Dispose() }
    if ($pythonDigest -ne $manifest.python_sha256) { throw 'Reviewed interpreter changed.' }
    function Quote-NativeArgument([string]$Value) {
        $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
        return '"' + [regex]::Replace($escaped, '(\\+)$', '$1$1') + '"'
    }
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $route.command
    $start.Arguments = ($route.args | ForEach-Object { Quote-NativeArgument $_ }) -join ' '
    $start.WorkingDirectory = $route.cwd
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    # No redirected/text-mediated pipes: preserve the caller's original OS wire.
    $process = [Diagnostics.Process]::Start($start)
    try { $process.WaitForExit(); $result = $process.ExitCode } finally { $process.Dispose() }
    exit $result
} catch {
    [Console]::Error.WriteLine('FreeCADMCPServer: ' + $_.Exception.Message)
    exit 1
}
