$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 or newer with Tkinter.' }
}
& '.\.venv\Scripts\python.exe' tools/install_dependencies.py
if ($LASTEXITCODE -ne 0) { throw 'Could not install dependencies. Check internet access.' }
Write-Host 'Ready. Double-click Start Room AC Control.cmd in the project root.'
