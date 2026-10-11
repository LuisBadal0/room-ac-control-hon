$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$executable = Join-Path $projectRoot 'runtime\RoomACControl\RoomACControl.exe'
if (-not (Test-Path -LiteralPath $executable)) { throw 'Build the portable app first.' }
$launcher = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $projectRoot 'Room AC Control.lnk'))
$launcher.TargetPath = $executable
$launcher.WorkingDirectory = $projectRoot
$launcher.IconLocation = $executable + ',0'
$launcher.Description = 'Room AC Control'
$launcher.Save()
