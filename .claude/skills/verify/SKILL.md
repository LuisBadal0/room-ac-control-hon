---
name: verify
description: Check a change to Room AC Control before calling it done or committing. Runs the cheap checks first, then the matching UI smoke checks, then opens the offline preview and looks at a picture of it. Use after any change to src/, tests/ or tools/, and whenever the user asks to verify, test or "see it working".
---

# Verify a change

The goal is evidence, not green ticks: say what ran, what it showed, and what was
not checked. Everything here is offline. Never sign in to a real account, never
start the app without `--preview`, and never send a command to a real AC.

Run every command from the repository root with `.venv\Scripts\python.exe`
(`python` below means that).

## 1. Cheap checks first

Stop at the first failure, fix it, and run the step again.

```
python -m ruff format src tests tools
python -m ruff check src tests tools
python -m mypy
python -m unittest discover -s tests
```

## 2. The smoke checks the change touches

Each smoke check opens real Tk windows offline. Run only the ones that match the
diff while working, and the whole set once before committing:

```
python tests/run_smoke.py ui_smoke.py tray_smoke.py   # named checks
python tests/run_smoke.py                             # all of them
```

| The diff touches | Run |
| --- | --- |
| `dashboard/`, `widgets.py`, `theme.py`, `button_theme.py` | `ui_smoke.py`, `dashboard_layout_smoke.py`, `theme_smoke.py` |
| `login_view.py`, `login_loading.py`, `secure_state.py` | `desktop_smoke.py` |
| `temperature_wheel.py`, `smooth.py` | `temperature_wheel_smoke.py` |
| `functions_view/`, `control_choices.py`, `choice_widgets.py`, `airflow.py` | `functions_scroll_smoke.py`, `ui_smoke.py` |
| `inline_timers.py`, `cloud_timers.py` | `timer_smoke.py` |
| `schedules*.py` | `schedules_smoke.py` |
| `room_history.py`, `routine_history.py`, `energy.py` | `history_smoke.py` |
| `weather.py` | `outside_smoke.py` |
| `tray.py`, `notifier.py` | `tray_smoke.py`, `notifications_smoke.py` |
| `live_updates.py`, `worker.py`, `controller.py` | `refresh_smoke.py` |
| `updates*.py`, `update_*.py` | `updates_smoke.py` |
| `window_header.py` | `window_header_smoke.py` |
| `i18n.py`, `translations.py` | `i18n_smoke.py` |
| `app.py`, packaging, assets | `self_test_smoke.py` |

If nothing in the table matches, run them all.

## 3. Look at it

For any change a user can see, take a picture of the offline preview and read
the PNG. Save it in the session scratchpad, never in the repository.

```
python tools/preview_capture.py <scratchpad>\dashboard.png
python tools/preview_capture.py <scratchpad>\bedroom.png --room 1
python tools/preview_capture.py <scratchpad>\login.png --screen login
```

Add `--theme dark` and `--language pt-PT` when the change involves colours or
text; Portuguese labels are longer and are where text gets cut off. Room 0 is on
and cooling; room 1 is off with a filter alert and unmeasured air quality.

Check the picture against what the change was meant to do, and for clipped or
overlapping text, wrong colours in the other theme, and layout that moved.
If the user approved a mockup, compare with it: it must match exactly.

The preview cannot show screens behind clicks (sheets, menus, the functions
list). For those, the matching smoke check is the evidence; say so.

## 4. Prove a fix

On a `fix/` branch, the new or changed test must fail without the fix. Stash or
revert only the source change (`git stash push -- src`), run the test and see it
fail for the reason the bug describes, then restore the fix and see it pass. A
test that passes either way does not guard against the bug.

## 5. Review the diff

Before opening the pull request, run `/code-review` on the branch. It follows
`REVIEW.md` from `main`. When the diff touches `updates.py`, `update_*.py`,
`secure_state.py`, `login_view.py`, `diagnostics.py`, `packaging/` or
`.github/workflows/`, run `/security-review` as well. Fix each Important finding,
or say in the PR why it does not apply.

## 6. When a check fails

- Fix the code, not the check. Do not loosen an assertion, skip a test, add a
  `sleep` or rerun until a flaky test passes. If a test is truly flaky and the
  cause cannot be found, tell the user instead of hiding it.
- After three rounds of fixes on the same failure, stop and report to the user:
  the failing command, its output, and what was tried.

## 7. Report

End with a short list for the PR's **Checks** section: each command and its
result, the pictures looked at (and what they showed), and what was not checked.
