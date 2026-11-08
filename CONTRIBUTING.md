# Contributing

Use Windows and Python 3.11 or newer; Python 3.13 is used for the portable build. Run `tools/Setup.ps1`, then `.venv\Scripts\python.exe -m room_ac_control --preview dashboard` for a preview with fictional rooms.

Install the developer checks once with `.venv\Scripts\python.exe tools/install_dependencies.py --dev` (hash-verified from `packaging/requirements-dev.lock`). Before submitting a change, format with `.venv\Scripts\python.exe -m ruff format src tests tools`, then run `.venv\Scripts\python.exe -m ruff check src tests tools`, `.venv\Scripts\python.exe -m mypy` (it checks the cloud-facing modules listed in `pyproject.toml`) and `.venv\Scripts\python.exe -m unittest discover -s tests -v`. Run the UI checks with `.venv\Scripts\python.exe tests/run_smoke.py`; it runs every `tests/*_smoke.py` script and fails if any fails. They use offline fixtures or disposable credentials. Never make automated tests operate a real AC or read a user's saved account.

To measure test coverage, run both suites under coverage and combine them:
`.venv\Scripts\python.exe -m coverage run -m unittest discover -s tests`, then
`.venv\Scripts\python.exe -m coverage run tests/run_smoke.py`, `coverage combine` and
`coverage report`. CI does the same and fails below the `fail_under` value in
`pyproject.toml`. `tests/test_pyhon_contract.py` runs a public, anonymized hOn
archive (`tests/fixtures/pyhon/`) through pyhOn and the app; when it fails after a
pyhOn update, the update changed something the app depends on.

Keep cloud work on the worker thread and UI changes on Tk's main thread. Preserve reported state separately from pending edits. Preview mode, login and status refresh must not send AC commands. Validate saved settings against current device capabilities before applying them.

For a local build run `tools/Build.ps1` and inspect the app, the runtime self-test report, the ZIP and, when the .NET SDK is installed, the MSI and Setup.exe from `tools/build_installers.py`. Test an installer with `msiexec /i <file>.msi /qn` and remove it with `msiexec /x <file>.msi /qn`; both are per-user and leave your saved settings alone. CI publishes releases: merging a pull request that bumps the version releases `v<version>`. Bump `pyproject.toml`, `src/room_ac_control/__init__.py`, `packaging/version_info.txt` and the README together; `tests/test_version.py` checks they match.

Use the hash-verified setup/build scripts rather than unverified `pip install -e .`.
Dependency changes must update all transitive pins and approved wheel hashes in
`requirements.lock`, `packaging/requirements-build.lock` and, for developer tools,
`packaging/requirements-dev.lock`. Review hashes against
the official package index and test in a fresh Windows virtual environment.
Action changes must use full upstream commit SHAs. See `docs/BUILD_VERIFICATION.md`.

CI is active in `.github/workflows/windows.yml`. Pull requests run the offline checks and portable Windows build. Workflow changes require GitHub workflow permissions; actions must remain pinned to full upstream commit SHAs.

Do not commit credentials, device serial numbers, cloud payload dumps, personal screenshots, local shortcuts, virtual environments or generated binaries. Issue reports should describe steps to reproduce and sanitize any logs or screenshots.

## Branch naming

Start each new feature on `feature/<descriptive-name>` and each bug fix on
`fix/<descriptive-name>`. Use lowercase, hyphenated names and submit a focused
pull request; keep implementation changes off `main`.
