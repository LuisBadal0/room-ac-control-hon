$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $PSScriptRoot 'Setup.ps1')
Set-Location -LiteralPath $projectRoot
& '.\.venv\Scripts\python.exe' tools/install_dependencies.py --build
if ($LASTEXITCODE -ne 0) { throw 'Could not install packaging tools.' }
& '.\.venv\Scripts\python.exe' tools/build_windows.py
if ($LASTEXITCODE -ne 0) { throw 'The Windows build failed.' }
if (Get-Command dotnet -ErrorAction SilentlyContinue) {
    & '.\.venv\Scripts\python.exe' tools/build_installers.py
    if ($LASTEXITCODE -ne 0) { throw 'The installer build failed.' }
} else {
    Write-Warning 'The .NET SDK was not found, so the MSI and Setup.exe were not built. The portable ZIP is ready.'
}
& (Join-Path $PSScriptRoot 'Create-Shortcut.ps1')
