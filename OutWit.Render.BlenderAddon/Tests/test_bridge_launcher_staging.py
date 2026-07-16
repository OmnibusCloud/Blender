"""Headless tests for bridge_launcher.stage_bridge_runtime.

The bridge must never run from inside the extension package: Windows locks a running
executable's image (and the process CWD), which made Blender's extension update fail with
"Failed to remove or relocate existing directory" while a bridge was alive. The launcher now
copies the bundled runtime to a per-user, version-keyed staging directory and launches from
there; these tests pin the staging, reuse, race-loss, and stale-version-cleanup behavior.

Run: python -m unittest (from OutWit.Render.BlenderAddon/Tests) — no bpy, no Blender required.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace

_PKG = "owrb_staging_test"

# Directory → (context, path) map behind the stubbed try_load_latest_context; tests populate it
# to simulate a live/dead bridge advertised in a staged version's BridgeSession.
_CONTEXTS: dict[str, tuple[object, str]] = {}


def _load_bridge_launcher():
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = []
    sys.modules[_PKG] = pkg

    sys.modules.setdefault("bpy", types.ModuleType("bpy"))

    client = types.ModuleType(_PKG + ".bridge_client")

    class BridgeClientError(Exception):
        pass

    client.BridgeClient = object
    client.BridgeClientError = BridgeClientError
    sys.modules[_PKG + ".bridge_client"] = client

    ctx = types.ModuleType(_PKG + ".bridge_context")
    ctx.FILE_PREFIX = "outwit_bridge_"
    ctx.FILE_SUFFIX = ".json"
    ctx.try_load_latest_context = lambda directory: _CONTEXTS.get(os.path.normpath(directory), (None, None))
    sys.modules[_PKG + ".bridge_context"] = ctx

    path = os.path.join(os.path.dirname(__file__), "..", "outwit_render_bridge", "bridge_launcher.py")
    spec = importlib.util.spec_from_file_location(_PKG + ".bridge_launcher", os.path.abspath(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


launcher = _load_bridge_launcher()


class StageBridgeRuntimeTests(unittest.TestCase):
    def setUp(self):
        _CONTEXTS.clear()
        self._temp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self._temp.name)
        self.package_root = base / "extension" / "omnibuscloud_render_bridge"
        self.staging_root = base / "staging"
        self.rid = launcher.get_runtime_identifier()

        bundle = self.package_root / "bridge" / self.rid / "self-contained"
        bundle.mkdir(parents=True)
        (self.package_root / "blender_manifest.toml").write_text(
            'schema_version = "1.0.0"\nid = "x"\nversion = "9.9.9"\n', encoding="utf-8"
        )
        self.bundled_exe = bundle / "OutWit.Render.BlenderBridge.exe"
        self.bundled_exe.write_bytes(b"bridge-v1")
        (bundle / "settings.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self._temp.cleanup()

    def _stage(self) -> pathlib.Path:
        return launcher.stage_bridge_runtime(self.bundled_exe, self.package_root, staging_root=self.staging_root)

    def test_executable_outside_the_package_is_returned_unchanged(self):
        external = pathlib.Path(self._temp.name) / "external" / "OutWit.Render.BlenderBridge.exe"
        external.parent.mkdir(parents=True)
        external.write_bytes(b"external")

        staged = launcher.stage_bridge_runtime(external, self.package_root, staging_root=self.staging_root)

        self.assertEqual(external, staged)
        self.assertFalse(self.staging_root.exists(), "an external executable must not create a staging dir")

    def test_bundled_executable_is_staged_outside_the_package(self):
        staged = self._stage()

        expected_dir = self.staging_root / "9.9.9" / self.rid
        self.assertEqual(expected_dir / self.bundled_exe.name, staged)
        self.assertEqual(b"bridge-v1", staged.read_bytes())
        self.assertTrue((expected_dir / "settings.json").exists(), "sibling runtime files must be copied")
        self.assertTrue((expected_dir / ".outwit-staged").exists(), "completed staging must be marked")
        self.assertFalse(staged.resolve().is_relative_to(self.package_root.resolve()))

    def test_staged_runtime_is_reused_on_later_launches(self):
        first = self._stage()
        self.bundled_exe.write_bytes(b"bridge-v2-rebuilt-in-place")

        second = self._stage()

        self.assertEqual(first, second)
        self.assertEqual(b"bridge-v1", second.read_bytes(), "same-version staging must be reused, not re-copied")

    def test_stale_versions_and_abandoned_temp_copies_are_removed(self):
        stale = self.staging_root / "1.0.0" / self.rid
        stale.mkdir(parents=True)
        (stale / "old.exe").write_bytes(b"old")
        abandoned = self.staging_root / ".tmp-deadbeef"
        abandoned.mkdir(parents=True)
        (abandoned / "half.exe").write_bytes(b"half")

        self._stage()

        self.assertFalse((self.staging_root / "1.0.0").exists(), "a stale version with no live bridge is removed")
        self.assertFalse(abandoned.exists(), "abandoned temp copies are removed")
        self.assertTrue((self.staging_root / "9.9.9").exists())

    def test_stale_version_with_live_bridge_is_left_alone(self):
        stale_session = self.staging_root / "1.0.0" / self.rid / "BridgeSession"
        stale_session.mkdir(parents=True)
        _CONTEXTS[os.path.normpath(str(stale_session))] = (
            SimpleNamespace(bridge_process_id=os.getpid()),
            str(stale_session / "outwit_bridge_ctx.json"),
        )

        self._stage()

        self.assertTrue((self.staging_root / "1.0.0").exists(), "a version whose bridge still runs must survive")

    def test_stale_version_with_dead_bridge_is_removed(self):
        dead_child = subprocess.Popen([sys.executable, "-c", "pass"])
        dead_child.wait(timeout=10)

        stale_session = self.staging_root / "1.0.0" / self.rid / "BridgeSession"
        stale_session.mkdir(parents=True)
        _CONTEXTS[os.path.normpath(str(stale_session))] = (
            SimpleNamespace(bridge_process_id=dead_child.pid),
            str(stale_session / "outwit_bridge_ctx.json"),
        )

        self._stage()

        self.assertFalse((self.staging_root / "1.0.0").exists())


class ReadAddonVersionTests(unittest.TestCase):
    def test_reads_version_from_manifest(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = pathlib.Path(temp_directory)
            (root / "blender_manifest.toml").write_text('id = "x"\nversion = "1.0.8"\n', encoding="utf-8")

            self.assertEqual("1.0.8", launcher.read_addon_version(root))

    def test_missing_manifest_falls_back(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            self.assertEqual("0.0.0", launcher.read_addon_version(pathlib.Path(temp_directory)))


if __name__ == "__main__":
    unittest.main()
