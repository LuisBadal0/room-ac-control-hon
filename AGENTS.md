# Project workflow

Create a new branch before implementing each feature or fix:

- `feature/<descriptive-name>` for new features.
- `fix/<descriptive-name>` for bug fixes.

Use lowercase names with hyphens. Keep each branch focused on its change and
do not implement changes directly on `main`. Publish changes on their branch
and open a pull request for review; merge only when the user requests it.

Keep credentials, account data, generated runtimes and local previews out of Git.
Verify AC controls with offline fixtures; do not send real AC commands in tests.
