<#
.SYNOPSIS
Explicitly select and install FreeCAD's app-owned framework host and standalone plugin.
.DESCRIPTION
Run normal setup first. Requires a clean committed checkout and a trusted local framework
wheel SHA-256. Builds and audits both application wheels, installs normal dependencies in
a dedicated immutable runtime, then initializes/starts this application's host. No CAD call
or GUI is made. Existing initialized host state is preserved rather than overwritten.
#>
param(
    [Parameter(Mandatory = $true)][string]$FrameworkWheel,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$FrameworkSha256,
    [string]$Workspace = '',
    [string]$FreeCADCmd = '',
    [string[]]$Extensions = @(),
    [ValidateRange(1024, 65535)][int]$Port = 8891,
    [switch]$NoStartMenuShortcut
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw 'Run scripts\Setup.ps1 first.' }
$FrameworkWheel = (Resolve-Path -LiteralPath $FrameworkWheel).Path
if ((Get-FileHash -LiteralPath $FrameworkWheel -Algorithm SHA256).Hash -ne $FrameworkSha256) {
    throw 'Framework wheel does not match the trusted SHA-256. Nothing was installed.'
}
$sourceCommit = & git -C $projectRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Install from a committed Git checkout.' }
$dirty = & git -C $projectRoot status --porcelain=v1
if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Commit or set aside tracked changes before framework installation.' }
$localOutput = Join-Path $projectRoot '.local'
$output = Join-Path $localOutput 'framework'
$marker = Join-Path $localOutput 'framework-installation.json'
if ((Test-Path -LiteralPath $marker) -or (Test-Path -LiteralPath (Join-Path $output 'state\settings.json'))) {
    throw 'Framework state already exists. Use Setup.ps1 to reinstall the selected plugin; use the documented publication/release/refresh workflow for backend updates. Existing state was preserved.'
}
$marketplaceJson = & codex plugin marketplace list --json
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Codex marketplaces before installation.' }
$marketplace = @((($marketplaceJson | ConvertFrom-Json).marketplaces) | Where-Object { $_.name -eq 'freecad-development' })
if ($marketplace.Count -gt 1 -or ($marketplace.Count -eq 1 -and $marketplace[0].root -ne $localOutput -and $marketplace[0].root -ne $output)) {
    throw 'FreeCAD marketplace points to another installation. Resolve that explicit selection before installing here.'
}
if (-not $Workspace) { $Workspace = Join-Path $projectRoot 'models' }
$Workspace = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Workspace)
if ($FreeCADCmd) { $FreeCADCmd = (Resolve-Path -LiteralPath $FreeCADCmd).Path }
$generation = [Guid]::NewGuid().ToString('N')
$packages = Join-Path $output "packages\$generation"
$runtime = Join-Path $output "runtimes\$generation"
$null = [IO.Directory]::CreateDirectory($packages)
& $pythonPath -m pip wheel --no-deps --wheel-dir $packages $projectRoot
if ($LASTEXITCODE -ne 0) { throw 'Backend wheel build failed.' }
& $pythonPath -m pip wheel --no-deps --wheel-dir $packages (Join-Path $projectRoot 'framework-host')
if ($LASTEXITCODE -ne 0) { throw 'Host wheel build failed.' }
$backendWheel = @(Get-ChildItem -LiteralPath $packages -Filter 'codex_freecad-*.whl')[0].FullName
$hostWheel = @(Get-ChildItem -LiteralPath $packages -Filter 'freecad_mcp_host-*.whl')[0].FullName
& $pythonPath (Join-Path $PSScriptRoot 'verify_framework_wheels.py') --backend-wheel $backendWheel --host-wheel $hostWheel --framework-wheel $FrameworkWheel --framework-sha256 $FrameworkSha256.ToLowerInvariant()
if ($LASTEXITCODE -ne 0) { throw 'Wheel audit failed before installation.' }
# Keep the exact trusted artifact with this application's own installation.
$frameworkCopy = Join-Path $packages ([IO.Path]::GetFileName($FrameworkWheel))
Copy-Item -LiteralPath $FrameworkWheel -Destination $frameworkCopy
& $pythonPath -m venv $runtime
if ($LASTEXITCODE -ne 0) { throw 'Host runtime creation failed.' }
$hostPython = Join-Path $runtime 'Scripts\python.exe'
& $hostPython -m pip install $backendWheel $hostWheel $frameworkCopy -r (Join-Path $projectRoot 'framework-host\requirements.lock')
if ($LASTEXITCODE -ne 0) { throw 'Host runtime installation failed; existing Codex plugin was preserved.' }
& $hostPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Host dependency check failed.' }
& $pythonPath (Join-Path $PSScriptRoot 'verify_framework_wheels.py') --backend-wheel $backendWheel --host-wheel $hostWheel --framework-wheel $frameworkCopy --framework-sha256 $FrameworkSha256.ToLowerInvariant() --site-packages (Join-Path $runtime 'Lib\site-packages')
if ($LASTEXITCODE -ne 0) { throw 'Installed package readback differs from audited wheels.' }
$publishArgs = @('-m', 'codex_freecad.framework_setup', '--workspace', $Workspace, '--output', $output, '--host-python', $hostPython, '--backend-python', $hostPython, '--installed')
if ($FreeCADCmd) { $publishArgs += @('--freecad-cmd', $FreeCADCmd) }
foreach ($directory in $Extensions) { $publishArgs += @('--extensions', $directory) }
& $hostPython @publishArgs
if ($LASTEXITCODE -ne 0) { throw 'Framework publication failed.' }
$hostArgs = @('-m', 'freecad_mcp_host', '--state', (Join-Path $output 'state'), '--publication', (Join-Path $output 'application.json'))
& $hostPython @hostArgs init --port $Port
if ($LASTEXITCODE -ne 0) { throw 'Framework state initialization failed.' }
& $hostPython @hostArgs start
if ($LASTEXITCODE -ne 0) { throw 'App host startup failed; existing Codex plugin was preserved.' }
# Use the same FreeCAD marketplace identity, replacing the direct plugin rather than duplicating it.
$codexHomePath = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$backup = Join-Path $output "backups\$generation"
$null = [IO.Directory]::CreateDirectory($backup)
[IO.File]::WriteAllText((Join-Path $backup 'marketplaces.json'), ($marketplaceJson -join "`n"), (New-Object Text.UTF8Encoding($false)))
$configPath = Join-Path $codexHomePath 'config.toml'
if (Test-Path -LiteralPath $configPath) { Copy-Item -LiteralPath $configPath -Destination (Join-Path $backup 'config.toml') }
$oldCache = Join-Path $codexHomePath 'plugins\cache\freecad-development\freecad-modeling'
if (Test-Path -LiteralPath $oldCache) { Copy-Item -LiteralPath $oldCache -Destination (Join-Path $backup 'freecad-modeling') -Recurse }
if ($marketplace.Count -eq 1 -and $marketplace[0].root -ne $output) {
    & codex plugin marketplace remove freecad-development
    if ($LASTEXITCODE -ne 0) { throw 'Cannot relocate the FreeCAD marketplace; previous plugin backup was retained.' }
}
& (Join-Path $PSScriptRoot 'Install-CodexPlugin.ps1') -Output $output
$record = @{
    schema_version = 1; application_id = 'freecad-mcp-server'; source_commit = $sourceCommit
    framework = '0.16.0'; mcp = '2.3.0'; framework_sha256 = $FrameworkSha256.ToLowerInvariant()
    output = $output; python = $hostPython; workspace = $Workspace
    packages = $packages
}
$pending = $marker + '.pending'
[IO.File]::WriteAllText($pending, ($record | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
Move-Item -LiteralPath $pending -Destination $marker
if (-not $NoStartMenuShortcut) {
    & (Join-Path $PSScriptRoot 'Create-StartMenuShortcut.ps1') -Workspace $Workspace
}
Write-Output 'FreeCAD app-owned framework host installed. Start a new Codex chat to load the updated standalone plugin.'
