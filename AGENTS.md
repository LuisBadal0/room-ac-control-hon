# Project workflow

Create a new branch before implementing each feature or fix:

- `feature/<descriptive-name>` for new features.
- `fix/<descriptive-name>` for bug fixes.

Use lowercase names with hyphens. Keep each branch focused on its change and
do not implement changes directly on `main`. Publish changes on their branch
and open a pull request for review; merge only when the user requests it.

Install the developer checks with
`.venv\Scripts\python.exe tools/install_dependencies.py --dev`. Before pushing, run
`.venv\Scripts\python.exe -m ruff format src tests tools`,
`.venv\Scripts\python.exe -m ruff check src tests tools` and
`.venv\Scripts\python.exe -m mypy`; CI runs all three.

Build with `tools/Build.ps1` (portable ZIP, then the MSI and Setup.exe via
`tools/build_installers.py`, which needs the .NET SDK). Run tests with
`.venv\Scripts\python.exe -m unittest discover -s tests -v`. Run the UI smoke checks with
`.venv\Scripts\python.exe tests/run_smoke.py`. The app version
lives in `pyproject.toml`, `src/room_ac_control/__init__.py`,
`packaging/version_info.txt` and `README.md`; `tests/test_version.py` checks them.

Update a locked Python dependency with
`.venv\Scripts\python.exe tools/update_lock.py <name>==<version>` (it refuses
releases newer than 14 days); `tests/test_dependency_pins.py` checks that
`requirements.txt` matches `requirements.lock`.

Keep credentials, account data, generated runtimes and local previews out of Git.
Verify AC controls with offline fixtures; do not send real AC commands in tests.
