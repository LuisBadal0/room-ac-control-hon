"""Every import in the app resolves, including imports made inside functions.

Many views import lazily inside methods, which only runs when that screen
opens. This walks each module's syntax tree, so a wrong relative import (for
example after moving code into a subpackage) fails here without opening the UI.
"""

import ast
import importlib
import importlib.util
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "room_ac_control"
OPTIONAL = {"winreg", "ctypes.wintypes"}  # Windows-only; present on the supported platform.


def module_name(path):
    parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


class ImportTests(unittest.TestCase):
    def test_every_import_resolves(self):
        files = sorted(PACKAGE.rglob("*.py"))
        self.assertGreater(len(files), 30)
        for path in files:
            name = module_name(path)
            package = name if path.name == "__init__.py" else name.rpartition(".")[0]
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    targets = [(alias.name, None) for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    base = "." * node.level + (node.module or "")
                    targets = [(base, alias.name) for alias in node.names]
                else:
                    continue
                for target, attribute in targets:
                    with self.subTest(module=name, line=node.lineno, target=target, name=attribute):
                        resolved = importlib.util.resolve_name(target, package) if target.startswith(".") else target
                        if resolved in OPTIONAL:
                            continue
                        module = importlib.import_module(resolved)
                        if attribute and attribute != "*" and not hasattr(module, attribute):
                            # `from package import submodule` names a module, not an attribute.
                            importlib.import_module(f"{resolved}.{attribute}")


if __name__ == "__main__":
    unittest.main()
