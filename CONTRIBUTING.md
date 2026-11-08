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

The main window lives in `src/room_ac_control/dashboard/`. `app.py` holds `App`: sign-in, device state, refresh, commands and the tray. `App` inherits the rest from mixins:

- `canvas.py`: drawing;
- `controls.py`: pointer and menu input;
- `schedule_actions.py`: timers and schedules;
- `preferences.py`: language, appearance and updates.

The fixed grid values are in `layout.py`. Put new dashboard code in the mixin for its area rather than back in `app.py`.

All functions lives in `src/room_ac_control/functions_view/`:

- `view.py`: the `FunctionsView` window, header, search, tabs, scrolling and footer;
- one mixin per tab: `settings_tab.py`, `everyday_tab.py`, `maintenance_tab.py` and `schedules_tab.py`;
- `sheets.py`: bottom sheets shared with the dashboard;
- `model.py`: tab, preset and search logic without Tk.

Many views import inside methods. `tests/test_imports.py` resolves every import, so a wrong relative path fails without opening the screen.

For a local build run `tools/Build.ps1` and inspect the app, the runtime self-test report, the ZIP and, when the .NET SDK is installed, the MSI and Setup.exe from `tools/build_installers.py`. Test an installer with `msiexec /i <file>.msi /qn` and remove it with `msiexec /x <file>.msi /qn`; both are per-user and leave your saved settings alone. CI publishes releases: merging a pull request that bumps the version releases `v<version>`. Bump `pyproject.toml`, `src/room_ac_control/__init__.py`, `packaging/version_info.txt` and the README together; `tests/test_version.py` checks they match.

Releases are batched. Every pull request that changes what users get adds a bullet under **Unreleased** in `CHANGELOG.md`, written for people using the app, and leaves the version alone. When the maintainer decides to release, a separate pull request on `chore/release-x.y.z`, titled `Release x.y.z (vx.y.z)`, does the rest:

- It bumps the version. Any breaking change makes it MAJOR, any new feature MINOR, and fixes alone PATCH.
- It renames **Unreleased** to `[x.y.z] - YYYY-MM-DD` and adds a new empty **Unreleased** above it.

Merging it publishes one release with all of those changes. CI turns the section into the GitHub release notes (`tools/release_notes.py`), followed by GitHub's list of merged pull requests. The build fails if the current version has no dated section with at least one bullet.

Use the hash-verified setup/build scripts rather than unverified `pip install -e .`.
Dependency changes must update all transitive pins and approved wheel hashes in
`requirements.lock`, `packaging/requirements-build.lock` and, for developer tools,
`packaging/requirements-dev.lock`. Review hashes against
the official package index and test in a fresh Windows virtual environment.
Action changes must use full upstream commit SHAs. See `docs/BUILD_VERIFICATION.md`.

Dependabot (`.github/dependabot.yml`) opens weekly pull requests for GitHub
Actions and the pins in `requirements.txt`, and monthly ones for the WiX tool.
Each waits 14 days after a release. A Python bump from Dependabot changes only
`requirements.txt`, so `tests/test_dependency_pins.py` fails until the locks
match: check out its branch and run
`.venv\Scripts\python.exe tools/update_lock.py <name>==<version>`, which writes
the SHA-256 of every PyPI wheel for that version into each lock that pins it.
Add any new transitive dependency by hand, then run `tools/Setup.ps1` and the
tests.

CI is active in `.github/workflows/windows.yml`. Pull requests run the offline checks and portable Windows build. Workflow changes require GitHub workflow permissions; actions must remain pinned to full upstream commit SHAs.

Do not commit credentials, device serial numbers, cloud payload dumps, personal screenshots, local shortcuts, virtual environments or generated binaries. Issue reports should describe steps to reproduce and sanitize any logs or screenshots.

## Branch naming

Start each new feature on `feature/<descriptive-name>` and each bug fix on
`fix/<descriptive-name>`. Use lowercase, hyphenated names and submit a focused
pull request; keep implementation changes off `main`.
