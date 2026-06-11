"""Headless tests for bridge_launcher.is_process_running (audit B3).

On Windows, os.kill(pid, 0) is NOT a liveness probe: os.kill calls TerminateProcess for any
signal other than CTRL_C/CTRL_BREAK, so the old implementation KILLED the bridge it was
"checking" (ensure_bridge_running and every status poll). These tests run the real function
against live/dead child processes and fail loudly if the probe ever becomes destructive again
(the probed child must SURVIVE the check).

Run: python -m unittest (from OutWit.Render.BlenderAddon/Tests) — no bpy, no Blender required.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
import types
import unittest

_PKG = "owrb_launcher_test"


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
    ctx.try_load_latest_context = lambda directory: (None, None)
    sys.modules[_PKG + ".bridge_context"] = ctx

    path = os.path.join(os.path.dirname(__file__), "..", "outwit_render_bridge", "bridge_launcher.py")
    spec = importlib.util.spec_from_file_location(_PKG + ".bridge_launcher", os.path.abspath(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


launcher = _load_bridge_launcher()


class IsProcessRunningTests(unittest.TestCase):
    def test_live_child_is_detected_and_survives_the_probe(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertTrue(launcher.is_process_running(child.pid))
            # THE point of the fix: probing must not kill the probed process (the old
            # os.kill(pid, 0) implementation terminated it on Windows).
            time.sleep(0.2)
            self.assertIsNone(child.poll(), "the probed process must survive the liveness check")
            self.assertTrue(launcher.is_process_running(child.pid))
        finally:
            child.kill()
            child.wait(timeout=10)

    def test_dead_child_is_detected(self):
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait(timeout=10)
        self.assertFalse(launcher.is_process_running(child.pid))

    def test_own_process_reads_alive(self):
        self.assertTrue(launcher.is_process_running(os.getpid()))

    def test_degenerate_pids_read_dead(self):
        self.assertFalse(launcher.is_process_running(0))
        self.assertFalse(launcher.is_process_running(-5))


if __name__ == "__main__":
    unittest.main()
