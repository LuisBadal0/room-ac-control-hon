"""Run the app's own --self-test from source, so a broken check fails before the build.

The build and the updater run the same self-test against the packaged app. It loads no
account and contacts nothing."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control import __version__
from room_ac_control.app import main, self_test

with tempfile.TemporaryDirectory() as folder:
    report = Path(folder) / "self-test.json"
    code = self_test(report)
    result = json.loads(report.read_text(encoding="utf-8"))
    assert code == 0 and result["ok"] is True, result
    # What the updater requires of a new version before it replaces the current one.
    assert result["version"] == __version__ and result["updates"] is True, result
    assert all(result[name] is True for name in ("tray", "mqtt", "encryption", "assets")), result

    # The command line reaches the same check and exits with its result.
    report.unlink()
    try:
        main(["--self-test", str(report)])
    except SystemExit as stop:
        assert stop.code == 0, stop.code
    else:
        raise AssertionError("--self-test did not exit")
    assert json.loads(report.read_text(encoding="utf-8"))["ok"] is True

print("Runtime self-test passed from source, directly and through the command line.")
