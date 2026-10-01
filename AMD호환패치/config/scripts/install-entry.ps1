param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    $child = Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $PSCommandPath + '"')) -Wait -PassThru
    exit $child.ExitCode
}
$py = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $py) { throw 'Python launcher (py.exe) is required. No runtime will be downloaded by this installer.' }
& $py.Source -3 "$root\config\scripts\naia_patch.py" install --package-root $root
exit $LASTEXITCODE
