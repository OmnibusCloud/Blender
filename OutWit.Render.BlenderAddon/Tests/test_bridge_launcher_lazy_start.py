"""Headless tests for the Phase-3 lazy-first-start split in bridge_launcher.

Covers (no bpy / no Blender):
- the panel-visibility marks that gate the lazy launch (note_panel_visible / panel_was_seen /
  panel_recently_visible);
- spawn_bridge_process — the worker-thread-SAFE spawn that must touch NO bpy, start the process and
  block until it publishes its connection context file, returning the PID. This is the contract the
  off-thread lazy launch depends on (the slow part runs on a worker; only the result write touches bpy).

Run: python -m unittest (from OutWit.Render.BlenderAddon/Tests).
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

_PKG = "owrb_lazy_test"
_PREFIX = "outwit_bridge_"
_SUFFIX = ".json"


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
    ctx.FILE_PREFIX = _PREFIX
    ctx.FILE_SUFFIX = _SUFFIX
    ctx.try_load_latest_context = lambda directory: (None, None)
    sys.modules[_PKG + ".bridge_context"] = ctx

    path = os.path.join(os.path.dirname(__file__), "..", "outwit_render_bridge", "bridge_launcher.py")
    spec = importlib.util.spec_from_file_location(_PKG + ".bridge_launcher", os.path.abspath(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


launcher = _load_bridge_launcher()


class PanelVisibilityTests(unittest.TestCase):
    def setUp(self):
        # Reset module-level visibility state so tests are order-independent.
        launcher._PANEL_SEEN = False
        launcher._LAST_PANEL_DRAW_MONOTONIC = 0.0

    def test_panel_not_seen_before_first_draw(self):
        self.assertFalse(launcher.panel_was_seen())
        self.assertFalse(launcher.panel_recently_visible())

    def test_note_panel_visible_latches_seen(self):
        launcher.note_panel_visible()
        self.assertTrue(launcher.panel_was_seen())
        self.assertTrue(launcher.panel_recently_visible())

    def test_recently_visible_respects_window(self):
        launcher.note_panel_visible()
        self.assertTrue(launcher.panel_recently_visible(within_seconds=60.0))
        # A draw far enough in the past is no longer "recent" (deterministic; avoids relying on the
        # coarse resolution of time.monotonic() between two back-to-back calls).
        launcher._LAST_PANEL_DRAW_MONOTONIC = time.monotonic() - 100.0
        self.assertFalse(launcher.panel_recently_visible(within_seconds=12.0))


class SpawnBridgeProcessTests(unittest.TestCase):
    def setUp(self):
        self._session = tempfile.mkdtemp(prefix="owrb_spawn_")
        self._orig_build = launcher.build_bridge_command
        # Replace the bridge command with a stub child that publishes the SAME context file the real
        # bridge does (outwit_bridge_<pid>.json in the session dir) and then idles, so we exercise the
        # real Popen + wait_for_bridge_context path without a built .NET binary.
        script = (
            "import os, sys, time\n"
            "d = sys.argv[1]\n"
            "open(os.path.join(d, '%s%%d%s' %% os.getpid()), 'w').write('{}')\n"
            "time.sleep(30)\n" % (_PREFIX, _SUFFIX)
        )
        launcher.build_bridge_command = lambda exe: [sys.executable, "-c", script, self._session]

    def tearDown(self):
        launcher.build_bridge_command = self._orig_build
        proc = getattr(launcher, "_LAUNCHED_BRIDGE_PROCESS", None)
        if proc is not None:
            try:
                proc.kill()
                proc.wait(timeout=10)
            except Exception:
                pass
        launcher._LAUNCHED_BRIDGE_PROCESS = None
        shutil.rmtree(self._session, ignore_errors=True)

    def test_spawn_publishes_context_and_returns_live_pid(self):
        pid = launcher.spawn_bridge_process(Path(sys.executable), Path(self._session))
        self.assertGreater(pid, 0)
        self.assertTrue(launcher.is_process_running(pid))
        self.assertTrue((Path(self._session) / f"{_PREFIX}{pid}{_SUFFIX}").exists())

    def test_spawn_raises_when_context_never_appears(self):
        # A child that never writes the context file must surface as a launch failure (marshalled back
        # to the main thread), not a silent hang — wait_for_bridge_context has a timeout.
        launcher.build_bridge_command = lambda exe: [sys.executable, "-c", "import time; time.sleep(30)"]
        from owrb_lazy_test.bridge_client import BridgeClientError

        with self.assertRaises(BridgeClientError):
            # Patch the timeout down so the test is quick.
            original = launcher.wait_for_bridge_context

            def _quick(process_id, session_directory, timeout_seconds=2.0):
                return original(process_id, session_directory, timeout_seconds=2.0)

            launcher.wait_for_bridge_context = _quick
            try:
                launcher.spawn_bridge_process(Path(sys.executable), Path(self._session))
            finally:
                launcher.wait_for_bridge_context = original


if __name__ == "__main__":
    unittest.main()
