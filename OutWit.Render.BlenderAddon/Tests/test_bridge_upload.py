"""Headless unit tests for the background upload path.

Large scenes and caches push through the bridge's background transfer: `upload_blend` /
`upload_file` keep their blocking signature (callers already run them on worker threads) but
internally start the transfer and poll status snapshots, so no single REST call ever spans the
whole cloud push (the old shape hit the 30s client timeout on multi-hundred-MB scenes).

Run: python -m unittest discover Tests — no bpy, no Blender required.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest

ADDON_DIR = pathlib.Path(__file__).resolve().parents[1] / "outwit_render_bridge"
PACKAGE_NAME = "owrb_upload_test"


def _load_module(name: str):
    if PACKAGE_NAME not in sys.modules:
        package = types.ModuleType(PACKAGE_NAME)
        package.__path__ = [str(ADDON_DIR)]
        sys.modules[PACKAGE_NAME] = package
    full = f"{PACKAGE_NAME}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, ADDON_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


bridge_models = _load_module("bridge_models")
bridge_client = _load_module("bridge_client")


def _upload_status(status: str, transfer_id: str = "t-1", result=None, error=None):
    return bridge_models.UploadStatusResponse(
        transfer_id=transfer_id,
        status=status,
        file_name="scene.blend",
        total_bytes=1024,
        result=result,
        error=error,
    )


class _ScriptedPostClient(bridge_client.BridgeClient):
    """BridgeClient whose REST layer is replaced by a script: the start call returns the first
    entry, each later poll the next one (the last entry repeats)."""

    def __init__(self, responses):
        super().__init__("unused-dir")
        self._responses = list(responses)
        self.calls = []

    def _post(self, method_name, parser, *payload):
        self.calls.append(method_name)
        response = self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return response


class UploadStatusResponseTests(unittest.TestCase):
    def test_parses_all_fields_including_nested_result(self):
        parsed = bridge_models.UploadStatusResponse.from_json({
            "TransferId": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
            "Status": "Completed",
            "FileName": "scene.blend",
            "TotalBytes": 130_000_000,
            "Result": {
                "Uploaded": True,
                "BlobId": "0f8fad5b-d9cb-469f-a165-70867728950e",
                "FileName": "scene.blend",
                "FileSize": 130_000_000,
                "Message": "Blend uploaded successfully.",
            },
            "Error": None,
        })

        self.assertEqual(parsed.status, "Completed")
        self.assertEqual(parsed.transfer_id, "7c9e6679-7425-40de-944b-e07fc1f90ae7")
        self.assertEqual(parsed.total_bytes, 130_000_000)
        self.assertIsNotNone(parsed.result)
        self.assertTrue(parsed.result.uploaded)
        self.assertEqual(parsed.result.blob_id, "0f8fad5b-d9cb-469f-a165-70867728950e")
        self.assertIsNone(parsed.error)

    def test_parses_failed_snapshot_with_error(self):
        parsed = bridge_models.UploadStatusResponse.from_json({
            "Status": "Failed",
            "Error": "Bridge is not connected to the cloud.",
        })

        self.assertEqual(parsed.status, "Failed")
        self.assertIsNone(parsed.result)
        self.assertEqual(parsed.error, "Bridge is not connected to the cloud.")


class RunUploadTests(unittest.TestCase):
    def test_polls_until_completed_and_returns_result(self):
        result = bridge_models.UploadBlendResponse(uploaded=True, blob_id="blob-1", file_name="scene.blend")
        client = _ScriptedPostClient([
            _upload_status("InProgress"),
            _upload_status("InProgress"),
            _upload_status("Completed", result=result),
        ])

        response = client.upload_blend("C:/scenes/scene.blend")

        self.assertIs(response, result)
        self.assertEqual(client.calls[0], "StartUploadBlendAsync")
        self.assertEqual(client.calls[1:], ["GetUploadStatusAsync", "GetUploadStatusAsync"])

    def test_completed_at_start_needs_no_polling(self):
        result = bridge_models.UploadBlendResponse(uploaded=True, blob_id="blob-1")
        client = _ScriptedPostClient([_upload_status("Completed", result=result)])

        response = client.upload_file("C:/scenes/cache_0001.vdb")

        self.assertIs(response, result)
        self.assertEqual(client.calls, ["StartUploadFileAsync"])

    def test_failed_upload_raises_with_bridge_error(self):
        client = _ScriptedPostClient([
            _upload_status("InProgress"),
            _upload_status("Failed", error="Bridge is not connected to the cloud."),
        ])

        with self.assertRaises(bridge_client.BridgeClientError) as raised:
            client.upload_blend("C:/scenes/scene.blend")

        self.assertIn("not connected", str(raised.exception))

    def test_cancelled_upload_raises(self):
        client = _ScriptedPostClient([
            _upload_status("InProgress"),
            _upload_status("Cancelled"),
        ])

        with self.assertRaises(bridge_client.BridgeClientError):
            client.upload_blend("C:/scenes/scene.blend")

    def test_completed_without_result_payload_raises(self):
        client = _ScriptedPostClient([_upload_status("Completed", result=None)])

        with self.assertRaises(bridge_client.BridgeClientError):
            client.upload_blend("C:/scenes/scene.blend")


if __name__ == "__main__":
    unittest.main()
