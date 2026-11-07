"""Entry point shared by the source launcher and Windows packager."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from room_ac_control.app import main

main()
