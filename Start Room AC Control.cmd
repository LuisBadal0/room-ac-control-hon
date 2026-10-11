@echo off
cd /d "%~dp0"
if exist "runtime\RoomACControl\RoomACControl.exe" (
    start "" "runtime\RoomACControl\RoomACControl.exe" %*
    exit /b 0
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "tools\launcher.py" %*
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 "tools\launcher.py" %*
    ) else (
        python "tools\launcher.py" %*
    )
)
if errorlevel 1 pause
