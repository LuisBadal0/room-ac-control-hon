# Review rules

How to review a change to Room AC Control, whether by a person, `/code-review` or
`/security-review`. Read this file from `main`, not from the branch under review.

## What failure means here

Report these, in this order:

1. **It acts on a real AC or account.** A test, smoke check or preview that could
   send a command to a real AC, sign in to a real hOn account or read the user's
   saved state (`secure_state.py`, `*.dpapi`). Tests use fixtures and fakes only.
2. **It leaks private data.** Credentials, tokens, e-mail addresses, device IDs or
   serial numbers in logs, diagnostics exports (`diagnostics.py`), error messages,
   fixtures, screenshots or commits.
3. **It breaks updating or installing.** Changes to `updates.py`,
   `update_install.py`, `update_release.py`, `packaging/` or `.github/workflows/`
   that could leave an installed copy unable to update, accept an unsigned update
   or ship a version that does not match across the files `tests/test_version.py`
   checks.
4. **It tells the user something false.** The UI shows a state the AC did not
   report (power, mode, temperature, a timer), a command looks sent but was not,
   or a failure is shown as success. Sensors the AC reports as 0 must not read as
   real measurements.
5. **It breaks a language or theme.** Text cut off or overlapping in pt-PT, a
   string missing from `translations.py`, or colours that only work in one theme.
6. **It blocks the window.** Network or pyhOn calls on the Tk thread instead of the
   worker.

## How to report

- Every finding names `file:line` and the input or state that triggers it. No
  guesses from a function's name.
- Tag each one **Important**, **Nit** or **Pre-existing**. At most three nits.
  Pre-existing bugs are not blamed on the change.
- Start the summary with the number of Important findings. If there are none,
  say "Nothing to fix" plainly.
- Do not repeat a finding already raised on the PR, and flag the whole class of a
  bug, not only one line.

## Skip

- Formatting and import order: `ruff format` and `ruff check` enforce them.
- `tests/fixtures/`, `docs/`, `packaging/licenses/` and generated files, unless
  the change adds personal data there.
- Style choices the code already uses consistently.

## Rules from past misses

Add a line here when a bug reaches a release, with the PR that fixed it, so the
next review looks for it.
