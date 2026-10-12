"""First-run setup for a source checkout; releases already include Python."""
from pathlib import Path
import subprocess
import sys
import venv
import hashlib
import json


def main():
    root=Path(__file__).resolve().parents[1]
    if sys.version_info < (3,11):
        raise RuntimeError("Install Python 3.11 or newer (with Tkinter), then run the launcher again.")
    environment=root/".venv"
    python=environment/"Scripts"/"python.exe"
    if not python.exists():
        print("Preparing Room AC Control. This first setup needs internet access.",flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    marker=environment/"room-ac-ready"
    expected=hashlib.sha256((root/"requirements.lock").read_bytes()).hexdigest()
    try:ready=json.loads(marker.read_text(encoding="utf-8")).get("runtime")==expected
    except (OSError,ValueError,AttributeError):ready=False
    if not ready:
        subprocess.run([str(python),str(root/"tools"/"install_dependencies.py")],check=True,cwd=root)
    subprocess.Popen([str(python.with_name("pythonw.exe")),str(root/"tools"/"run.py"),*sys.argv[1:]],cwd=root)


if __name__=="__main__":
    try:
        main()
    except Exception as error:
        print(f"Setup could not finish: {error}",file=sys.stderr)
        print("Use the portable Windows ZIP for a version that includes Python and all dependencies.",file=sys.stderr)
        sys.exit(1)
