@echo off
setlocal EnableExtensions DisableDelayedExpansion
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\InstallAndRun.ps1" -InstallOnly %*
exit /b %errorlevel%
