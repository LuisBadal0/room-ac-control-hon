# Contributing

Use Windows and Python 3.11 or newer; Python 3.13 is used for the portable build. Run `tools/Setup.ps1`, then `.venv\Scripts\python.exe -m room_ac_control --preview dashboard` for a preview with fictional rooms.

Run `.venv\Scripts\python.exe -m unittest discover -s tests -v` before submitting a change. UI checks live in `tests/ui_smoke.py`, `tests/refresh_smoke.py`, `tests/desktop_smoke.py` and `tests/window_header_smoke.py`. They use offline fixtures or disposable credentials. Never make automated tests operate a real AC or read a user's saved account.

Keep cloud work on the worker thread and UI changes on Tk's main thread. Preserve reported state separately from pending edits. Preview mode, login and status refresh must not send AC commands. Validate saved settings against current device capabilities before applying them.

For a portable release run `tools/Build.ps1`. Inspect the app, the runtime self-test report and the ZIP before publishing. Include generated dependency notices and the complete runtime folder.

Optional CI is available in `packaging/github-workflow.yml`. It is a template rather than an active workflow; enabling it requires GitHub workflow permissions.

Do not commit credentials, device serial numbers, cloud payload dumps, personal screenshots, local shortcuts, virtual environments or generated binaries. Issue reports should describe steps to reproduce and sanitize any logs or screenshots.
