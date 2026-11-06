# Project workflow

Create a new branch before implementing each feature or fix:

- `feature/<descriptive-name>` for new features.
- `fix/<descriptive-name>` for bug fixes.

Use lowercase names with hyphens. Keep each branch focused on its change and
do not implement changes directly on `main`. Publish changes on their branch
and open a pull request for review; merge only when the user requests it.

Build with `tools/Build.ps1` (portable ZIP, then the MSI and Setup.exe via
`tools/build_installers.py`, which needs the .NET SDK). Run tests with
`.venv\Scripts\python.exe -m unittest discover -s tests -v`. The app version
lives in `pyproject.toml`, `src/room_ac_control/__init__.py`,
`packaging/version_info.txt` and `README.md`; `tests/test_version.py` checks them.

Keep credentials, account data, generated runtimes and local previews out of Git.
Verify AC controls with offline fixtures; do not send real AC commands in tests.
