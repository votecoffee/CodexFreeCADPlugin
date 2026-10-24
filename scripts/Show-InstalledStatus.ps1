param([string]$InstallRoot = '')
$ErrorActionPreference = 'Stop'
if (-not $InstallRoot) { $InstallRoot = $PSScriptRoot }
$pointer = Get-Content -LiteralPath (Join-Path $InstallRoot 'launcher\current.json') -Raw | ConvertFrom-Json
if ($pointer.snapshot -notmatch '^[a-f0-9]{64}$') { throw 'Invalid installed snapshot.' }
$manifestBytes = [IO.File]::ReadAllBytes((Join-Path $InstallRoot "launcher\snapshots\$($pointer.snapshot)\manifest.json"))
$hasher = [Security.Cryptography.SHA256]::Create()
try { $digest = [BitConverter]::ToString($hasher.ComputeHash($manifestBytes)).Replace('-','').ToLowerInvariant() }
finally { $hasher.Dispose() }
if ($digest -ne $pointer.snapshot) { throw 'Installed selection changed.' }
$manifest = [Text.Encoding]::UTF8.GetString($manifestBytes) | ConvertFrom-Json
$InstallRoot = $manifest.installation_root
if ([IO.Path]::GetFileName($manifest.python) -ne 'pythonw.exe') { throw 'Unexpected selected interpreter.' }
$consolePython = Join-Path (Split-Path -Parent $manifest.python) 'python.exe'
$consoleStream = [IO.File]::OpenRead($consolePython)
$consoleHasher = [Security.Cryptography.SHA256]::Create()
try { $consoleDigest = [BitConverter]::ToString($consoleHasher.ComputeHash($consoleStream)).Replace('-','').ToLowerInvariant() }
finally { $consoleHasher.Dispose(); $consoleStream.Dispose() }
if ($consoleDigest -ne $manifest.python_console_sha256) { throw 'Reviewed console interpreter changed.' }
& $consolePython -I -S -B (Join-Path $InstallRoot 'Inspect-Selection.py') --root $InstallRoot
if ($LASTEXITCODE -ne 0) { throw 'Installed selection is missing, tampered or unavailable.' }
