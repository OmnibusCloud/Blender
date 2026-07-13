from __future__ import annotations

import ast
import pathlib
import unittest


PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "outwit_render_bridge"

# Stdlib modules the addon uses via ``<module>.<attr>``. A reference to any of these without a matching
# import is a NameError the moment that code path runs — and because several addon modules ``import bpy``
# they cannot be imported outside Blender, so a plain unit test never exercises them (this is exactly how
# ``bridge_operators`` shipped a ``re.sub`` call with no ``import re``, crashing the local bake). This test
# statically (AST-only, no import) verifies every such reference is backed by an import.
_STDLIB_MODULES = {
    "re", "os", "json", "sys", "subprocess", "math", "time", "glob",
    "shutil", "tempfile", "pathlib", "uuid", "datetime", "collections",
    "itertools", "io", "zipfile",
}


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _stdlib_modules_used(tree: ast.AST) -> set[str]:
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in _STDLIB_MODULES:
                used.add(node.value.id)
    return used


class ModuleImportHygieneTests(unittest.TestCase):
    def test_every_stdlib_module_used_is_imported(self) -> None:
        modules = sorted(PACKAGE_ROOT.glob("*.py"))
        self.assertGreater(len(modules), 0, f"no addon modules found under {PACKAGE_ROOT}")

        problems: list[str] = []
        for path in modules:
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            missing = _stdlib_modules_used(tree) - _imported_names(tree)
            for module in sorted(missing):
                problems.append(f"{path.name}: uses '{module}.' but never imports '{module}'")

        self.assertEqual(problems, [], "missing stdlib imports:\n" + "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
