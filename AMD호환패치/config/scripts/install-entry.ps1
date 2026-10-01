param([string]$Language, [string]$AppRoot, [string]$BackendProfile)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    $childArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $PSCommandPath + '"'))
    if ($Language) { $childArgs += @('-Language', $Language) }
    if ($AppRoot) { $childArgs += @('-AppRoot', ('"' + $AppRoot + '"')) }
    if ($BackendProfile) { $childArgs += @('-BackendProfile', $BackendProfile) }
    $child = Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $childArgs -Wait -PassThru
    exit $child.ExitCode
}
$py = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $py) { throw 'Python launcher (py.exe) is required. No runtime will be downloaded by this installer.' }
$cliArgs = @('-3', "$root\config\scripts\naia_patch.py", 'install', '--package-root', $root)
if ($Language) { $cliArgs += @('--language', $Language) }
if ($AppRoot) { $cliArgs += @('--app-root', $AppRoot) }
if ($BackendProfile) { $cliArgs += @('--backend-profile', $BackendProfile) }
$oldEncoding = [Console]::OutputEncoding
$hadPythonEncoding = Test-Path Env:PYTHONIOENCODING
$oldPythonEncoding = $env:PYTHONIOENCODING
$childExit = 1
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $env:PYTHONIOENCODING = 'utf-8'
    & $py.Source @cliArgs
    $childExit = $LASTEXITCODE
} finally {
    [Console]::OutputEncoding = $oldEncoding
    if ($hadPythonEncoding) { $env:PYTHONIOENCODING = $oldPythonEncoding }
    else { Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue }
}
exit $childExit
