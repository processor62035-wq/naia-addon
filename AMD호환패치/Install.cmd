@echo off
setlocal
set "PATCH_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PATCH_ROOT%config\scripts\install-entry.ps1" %*
exit /b %errorlevel%
