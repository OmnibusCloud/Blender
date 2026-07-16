"""Headless unit tests for the background result-download path.

Large results (video, frame archives) stream through the bridge's background transfer: the addon
starts it once and polls status snapshots, so no REST call ever blocks for the whole download (the
old synchronous shape hit the 30s client timeout on multi-hundred-MB videos). These tests cover the
pure pieces without Blender: DownloadStatusResponse parsing, DownloadMonitor's start+poll
lifecycle against a fake client, and the byte formatter behind the progress text.

Run: python -m unittest discover Tests — no bpy, no Blender required.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import time
import types
import unittest
from types import SimpleNamespace as NS

ADDON_DIR = pathlib.Path(__file__).resolve().parents[1] / "outwit_render_bridge"
PACKAGE_NAME = "owrb_download_test"


def _ensure_package() -> None:
    if PACKAGE_NAME in sys.modules:
        return
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(ADDON_DIR)]
    sys.modules[PACKAGE_NAME] = package


def _load_module(name: str):
    """Loads a real addon module under the test package (relative imports resolve to siblings)."""
    _ensure_package()
    full = f"{PACKAGE_NAME}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, ADDON_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


def _load_bridge_status():
    """bridge_status imports bridge_engine_routing (bpy-bound) — stub it, load the rest for real."""
    _ensure_package()
    routing_name = f"{PACKAGE_NAME}.bridge_engine_routing"
    if routing_name not in sys.modules:
        routing = types.ModuleType(routing_name)
        routing.recommended_render_mode = lambda scene: "Still"
        routing.render_mode_matches_recommendation = lambda current, recommended: True
        routing.scene_frame_count = lambda scene: 1
        routing.suggested_render_mode = lambda scene: "Still"
        sys.modules[routing_name] = routing
    return _load_module("bridge_status")


bridge_models = _load_module("bridge_models")
bridge_async = _load_module("bridge_async")
bridge_status = _load_bridge_status()


class _FakeDownloadClient:
    """Scripted bridge client: one start response/error, then a sequence of poll responses.

    The last poll entry repeats forever; an entry that is an Exception is raised instead.
    """

    def __init__(self, start=None, start_error=None, polls=None):
        self._start = start
        self._start_error = start_error
        self._polls = list(polls or [])
        self.start_calls = 0
        self.poll_calls = 0

    def start_download_result(self, job_id):
        self.start_calls += 1
        if self._start_error is not None:
            raise self._start_error
        return self._start

    def get_download_result_status(self, job_id):
        self.poll_calls += 1
        entry = self._polls[min(self.poll_calls - 1, len(self._polls) - 1)]
        if isinstance(entry, Exception):
            raise entry
        return entry


def _status(status: str, **kwargs) -> NS:
    return NS(status=status, **kwargs)


def _wait_for_terminal(monitor, timeout_seconds: float = 5.0):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        snapshot, error, terminal = monitor.snapshot()
        if terminal:
            return snapshot, error
        time.sleep(0.01)
    raise AssertionError("DownloadMonitor did not reach a terminal state in time")


class DownloadStatusResponseTests(unittest.TestCase):
    def test_parses_all_fields_including_nested_result(self):
        payload = {
            "JobId": "0f8fad5b-d9cb-469f-a165-70867728950e",
            "Status": "Completed",
            "TotalBytes": 300_000_000,
            "DownloadedBytes": 300_000_000,
            "Progress": 1.0,
            "ItemCount": 2,
            "ItemsCompleted": 2,
            "CurrentFileName": "",
            "Result": {
                "Downloaded": True,
                "JobId": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "BlobId": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                "FileName": "render.mp4",
                "LocalPath": "C:/cache/render.mp4",
                "FileSize": 300_000_000,
                "Items": [
                    {"BlobId": "7c9e6679-7425-40de-944b-e07fc1f90ae7", "FileName": "render.mp4",
                     "LocalPath": "C:/cache/render.mp4", "FileSize": 300_000_000},
                ],
                "Message": "Result downloaded successfully.",
            },
            "Error": None,
        }

        parsed = bridge_models.DownloadStatusResponse.from_json(payload)

        self.assertEqual(parsed.status, "Completed")
        self.assertEqual(parsed.total_bytes, 300_000_000)
        self.assertEqual(parsed.downloaded_bytes, 300_000_000)
        self.assertEqual(parsed.progress, 1.0)
        self.assertEqual(parsed.item_count, 2)
        self.assertEqual(parsed.items_completed, 2)
        self.assertIsNotNone(parsed.result)
        self.assertTrue(parsed.result.downloaded)
        self.assertEqual(parsed.result.file_name, "render.mp4")
        self.assertEqual(len(parsed.result.items), 1)
        self.assertIsNone(parsed.error)

    def test_parses_in_progress_snapshot_without_result(self):
        parsed = bridge_models.DownloadStatusResponse.from_json({
            "JobId": "0f8fad5b-d9cb-469f-a165-70867728950e",
            "Status": "InProgress",
            "TotalBytes": 100,
            "DownloadedBytes": 25,
            "Progress": 0.25,
            "ItemCount": 1,
            "ItemsCompleted": 0,
            "CurrentFileName": "render.mp4",
        })

        self.assertEqual(parsed.status, "InProgress")
        self.assertEqual(parsed.current_file_name, "render.mp4")
        self.assertIsNone(parsed.result)

    def test_parses_failed_snapshot_with_error(self):
        parsed = bridge_models.DownloadStatusResponse.from_json({
            "Status": "Failed",
            "Error": "Bridge is not connected to the cloud.",
        })

        self.assertEqual(parsed.status, "Failed")
        self.assertEqual(parsed.error, "Bridge is not connected to the cloud.")


class DownloadMonitorTests(unittest.TestCase):
    def _make_monitor(self, client) -> "bridge_async.DownloadMonitor":
        return bridge_async.DownloadMonitor("unused-dir", "job-1", interval_seconds=0.01, client=client)

    def test_reaches_terminal_when_poll_returns_completed(self):
        client = _FakeDownloadClient(
            start=_status("InProgress"),
            polls=[_status("InProgress"), _status("Completed")],
        )

        snapshot, error = _wait_for_terminal(self._make_monitor(client).start())

        self.assertEqual(snapshot.status, "Completed")
        self.assertIsNone(error)
        self.assertEqual(client.start_calls, 1)

    def test_terminal_immediately_when_start_returns_terminal(self):
        client = _FakeDownloadClient(start=_status("Completed"))

        snapshot, error = _wait_for_terminal(self._make_monitor(client).start())

        self.assertEqual(snapshot.status, "Completed")
        self.assertIsNone(error)
        self.assertEqual(client.poll_calls, 0, "a terminal start snapshot must not be polled further")

    def test_start_failure_is_terminal_with_error(self):
        client = _FakeDownloadClient(start_error=RuntimeError("bridge unreachable"))

        snapshot, error = _wait_for_terminal(self._make_monitor(client).start())

        self.assertIsNone(snapshot)
        self.assertIsInstance(error, RuntimeError)

    def test_cancelled_status_is_terminal(self):
        client = _FakeDownloadClient(
            start=_status("InProgress"),
            polls=[_status("Cancelled")],
        )

        snapshot, _ = _wait_for_terminal(self._make_monitor(client).start())

        self.assertEqual(snapshot.status, "Cancelled")

    def test_gives_up_after_consecutive_poll_failures(self):
        client = _FakeDownloadClient(
            start=_status("InProgress"),
            polls=[RuntimeError("bridge went away")],
        )

        snapshot, error = _wait_for_terminal(self._make_monitor(client).start())

        self.assertEqual(snapshot.status, "InProgress", "the last good snapshot stays available")
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(client.poll_calls, bridge_async.DownloadMonitor.MAX_CONSECUTIVE_POLL_FAILURES)


class FormatBytesTests(unittest.TestCase):
    def test_formats_each_magnitude(self):
        cases = [
            (0, "0 B"),
            (512, "512 B"),
            (2048, "2.0 KB"),
            (300 * 1024 * 1024, "300.0 MB"),
            (int(1.3 * 1024 ** 3), "1.3 GB"),
            (2 * 1024 ** 4, "2.0 TB"),
        ]
        for byte_count, expected in cases:
            with self.subTest(byte_count=byte_count):
                self.assertEqual(bridge_status.format_bytes(byte_count), expected)

    def test_negative_input_clamps_to_zero(self):
        self.assertEqual(bridge_status.format_bytes(-5), "0 B")


if __name__ == "__main__":
    unittest.main()
