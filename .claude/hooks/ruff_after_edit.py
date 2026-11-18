"""Claude Code PostToolUse hook: format and lint a Python file right after it is edited.

Reads the hook payload on stdin. For a .py file under src/, tests/ or tools/ it runs
`ruff format` and then `ruff check`. Lint errors go to stderr with exit code 2, which
Claude Code passes back to the agent so it fixes them before moving on. Anything else
(other files, ruff missing) exits 0 and stays silent.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKED = ("src", "tests", "tools")


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    data = payload.get("tool_input") or {}
    raw = data.get("file_path") or (payload.get("tool_response") or {}).get("filePath")
    if not raw:
        return 0
    path = Path(raw).resolve()
    if path.suffix != ".py" or not path.is_file():
        return 0
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        return 0
    if relative.parts[0] not in CHECKED:
        return 0
    ruff = [sys.executable, "-m", "ruff"]
    try:
        subprocess.run([*ruff, "format", "--quiet", str(relative)], cwd=ROOT, check=False)
        result = subprocess.run(
            [*ruff, "check", "--output-format", "concise", str(relative)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    except OSError:
        return 0
    if result.returncode == 1:
        print(f"ruff check found problems in {relative}:\n{result.stdout.strip()}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
