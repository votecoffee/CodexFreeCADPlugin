<#
.SYNOPSIS
Create or update the current user's FreeCADMCPServer Start menu shortcut.
.PARAMETER ShortcutDirectory
Optional shortcut output directory; defaults to the current user's Programs folder.
#>
param(
    [string]$InstallRoot = '',
    [string]$Workspace = '',
    [string]$FreeCADCmd = '',
    [ValidateSet('headless', 'live')]
    [string]$Mode = 'headless',
    [string]$ShortcutDirectory = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Workspace) { $Workspace = 'models' }
if (-not [IO.Path]::IsPathRooted($Workspace)) {
    $Workspace = Join-Path $projectRoot $Workspace
}
$Workspace = [IO.Path]::GetFullPath($Workspace)
if ($FreeCADCmd) {
    $FreeCADCmd = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($FreeCADCmd)
}
if (-not $ShortcutDirectory) {
    $ShortcutDirectory = [Environment]::GetFolderPath('Programs')
    if (-not $ShortcutDirectory) { throw 'The current user Start menu is unavailable.' }
}
$ShortcutDirectory = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ShortcutDirectory)
if (-not $InstallRoot) { $InstallRoot = Join-Path $env:LOCALAPPDATA 'FreeCADMCPServer' }
$launcher = Join-Path $InstallRoot 'Show-Status.ps1'
$icon = Join-Path $InstallRoot 'assets\FreeCADMCPServer.ico'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
foreach ($required in @($launcher, $icon, $powershell)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Shortcut dependency missing: $required"
    }
}

function Quote-NativeArgument([string]$Value) {
    # Win32 argv quoting: double slashes preceding a quote or a closing quote.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    return '"' + [regex]::Replace($escaped, '(\\+)$', '$1$1') + '"'
}

$arguments = @('-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit',
    '-File', $launcher, '-InstallRoot', $InstallRoot)
$argumentLine = ($arguments | ForEach-Object { Quote-NativeArgument $_ }) -join ' '
$null = [IO.Directory]::CreateDirectory($ShortcutDirectory)
$shortcutPath = Join-Path $ShortcutDirectory 'FreeCADMCPServer.lnk'
$shell = $null
$shortcut = $null
try {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $powershell
    $shortcut.Arguments = $argumentLine
    $shortcut.WorkingDirectory = Join-Path $InstallRoot 'cwd'
    $shortcut.IconLocation = "$icon,0"
    $shortcut.Description = 'FreeCADMCPServer installed selection and connection status'
    $shortcut.WindowStyle = 1
    $shortcut.Save()
} finally {
    if ($null -ne $shortcut) { $null = [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut) }
    if ($null -ne $shell) { $null = [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) }
}
Write-Output "Start menu shortcut: $shortcutPath"
