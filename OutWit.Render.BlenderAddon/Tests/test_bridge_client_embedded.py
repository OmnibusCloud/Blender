"""The embedded (native-SDK) client against a fake pyoc client — no Blender, no network,
no native library (05-blender-sdk-migration.md, 12.2 "adapter").

What is asserted is the request-document composition of every launch method:
the script name, the positional parameter order, the enum names, the scope,
and the attachment shape — the exact contract the server door materializes.
Plus the event folding behind sign-in/connect, uploads and downloads.

Run: python -m unittest Tests.test_bridge_client_embedded
"""
from __future__ import annotations

import importlib
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest

ADDON_DIR = pathlib.Path(__file__).resolve().parents[1] / "outwit_render_bridge"
PACKAGE_NAME = "owrb_embedded_test"

GROUP = "11111111-1111-1111-1111-111111111111"
PROJECT = "22222222-2222-2222-2222-222222222222"


def _bootstrap_package():
    if PACKAGE_NAME in sys.modules:
        return
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(ADDON_DIR)]
    sys.modules[PACKAGE_NAME] = package


def _load(name: str):
    _bootstrap_package()
    return importlib.import_module(f"{PACKAGE_NAME}.{name}")


bridge_models = _load("bridge_models")
pyoc = _load("vendor.pyoc")
render = _load("vendor.render_documents")
embedded = _load("bridge_client_embedded")


class FakeEvent:
    def __init__(self, type_: str, operation=None, payload=None, state=None, status=None, message=""):
        self.type = type_
        self.operation = operation
        self.payload = payload or {}
        self.state = state
        self.status = status
        self.message = message
        self.raw = json.dumps({"type": type_, "operation": operation, "payload": self.payload})
        self.sequence = 0

    @property
    def is_terminal(self):
        return self.type in (pyoc.events.OPERATION_COMPLETED, pyoc.events.OPERATION_FAILED)

    @property
    def is_completed(self):
        return self.type == pyoc.events.OPERATION_COMPLETED

    @property
    def is_failed(self):
        return self.type == pyoc.events.OPERATION_FAILED


class FakePyocClient:
    """Records every call; completes operations with canned payloads through wait()/events."""

    def __init__(self, server_url, identity_url=None):
        self.server_url = server_url
        self.identity_url = identity_url
        self.calls: list[tuple] = []
        self.requests: list[dict] = []
        self.next_operation = 100
        self.queue: list = []
        self.job_status = "Completed"
        self.variables: dict[str, dict] = {}
        self.variable_errors: dict[str, str] = {}
        self.assets: dict[str, dict] = {}
        self.attached_store = None

    # -- helpers ------------------------------------------------------------
    def _op(self, name, *args, completion=None, events=None, manual=False):
        self.calls.append((name, *args))
        self.next_operation += 1
        operation = self.next_operation
        if manual:
            return operation  # the test completes it with emit()
        # One queue for everything, like the real client: progress/state events carry the
        # operation id (or none), the terminal event closes it.
        for event in events or []:
            if event.operation is None and event.type == pyoc.events.OPERATION_PROGRESS:
                event.operation = operation
            self.queue.append(event)
        self.queue.append(FakeEvent(pyoc.events.OPERATION_COMPLETED, operation, completion or {}))
        return operation

    def emit(self, event):
        self.queue.append(event)

    # -- pyoc.Client surface -----------------------------------------------
    def credentials_attach(self, path, max_age_days=0):
        self.attached_store = path

    restore_succeeds = False

    def credentials_restore(self):
        self.calls.append(("credentials_restore",))
        self.next_operation += 1
        operation = self.next_operation
        if self.restore_succeeds:
            self.queue.append(FakeEvent(pyoc.events.OPERATION_COMPLETED, operation,
                                        {"credentials": {"schemaVersion": 1, "restored": True}}))
        else:
            self.queue.append(FakeEvent(pyoc.events.OPERATION_FAILED, operation, {"status": pyoc.OC_NOT_FOUND, "message": "no persisted session"},
                                        status=pyoc.OC_NOT_FOUND, message="no persisted session"))
        return operation

    def login_browser(self):
        return self._op("login_browser", manual=True)

    def logout(self):
        return self._op("logout")

    def connect(self):
        return self._op("connect", events=[FakeEvent(pyoc.events.CONNECTION_STATE, None, {"state": "connecting"}, state="connecting"),
                                            FakeEvent(pyoc.events.CONNECTION_STATE, None, {"state": "connected"}, state="connected")])

    def close(self):
        return self._op("close")

    def scopes_list(self):
        return self._op("scopes_list", completion={"scopes": {
            "canRunOnAllClients": True,
            "groups": [{"groupId": GROUP, "name": "Group", "description": None}],
            "projects": [{"projectId": PROJECT, "name": "Project", "assignedGroupId": GROUP, "assignedGroupName": "Group"}],
        }})

    def asset_upload_file(self, path):
        return self._op("asset_upload_file", path,
                        events=[FakeEvent(pyoc.events.OPERATION_PROGRESS, None, {"completedBytes": 10, "totalBytes": 20})],
                        completion={"asset": {"assetId": "asset-1", "fileName": os.path.basename(path), "size": 20}})

    def job_submit(self, request):
        data = request.to_dict() if hasattr(request, "to_dict") else json.loads(request)
        self.requests.append(data)
        return self._op("job_submit", completion={"job": {"jobId": f"job-{len(self.requests)}"}})

    def job_get(self, job_id):
        return self._op("job_get", job_id, completion={"job": {"jobId": job_id, "scriptName": "S", "status": self.job_status, "progress": 1.0}})

    def job_cancel(self, job_id):
        return self._op("job_cancel", job_id, completion={"job": {"jobId": job_id}})

    def job_get_variable(self, job_id, variable):
        error = self.variable_errors.get(job_id)
        if error:
            self.calls.append(("job_get_variable", job_id, variable))
            self.next_operation += 1
            operation = self.next_operation
            self.queue.append(FakeEvent(pyoc.events.OPERATION_FAILED, operation, {"status": pyoc.OC_INTERNAL_ERROR, "message": error},
                                        status=pyoc.OC_INTERNAL_ERROR, message=error))
            return operation
        return self._op("job_get_variable", job_id, variable, completion={"job": {"jobId": job_id}, "value": self.variables.get(job_id, {"kind": "null"})})

    def job_download_result(self, job_id, target):
        pathlib.Path(target).write_bytes(b"png")
        return self._op("job_download_result", job_id, target,
                        events=[FakeEvent(pyoc.events.OPERATION_PROGRESS, None, {"completedBytes": 3, "totalBytes": 3})],
                        completion={"job": {"jobId": job_id}, "asset": {"assetId": "res-1", "fileName": "still.png", "size": 3}})

    def asset_query(self, asset_id):
        asset = self.assets.get(asset_id) or {"assetId": asset_id, "fileName": f"{asset_id}.bin", "size": 3}
        return self._op("asset_query", asset_id, completion={"asset": asset})

    def asset_download_file(self, asset_id, target):
        asset = self.assets.get(asset_id) or {"assetId": asset_id, "size": 3}
        size = int(asset.get("size") or 3)
        pathlib.Path(target).write_bytes(b"x" * size)
        return self._op("asset_download_file", asset_id, target,
                        events=[FakeEvent(pyoc.events.OPERATION_PROGRESS, None, {"completedBytes": size, "totalBytes": size})],
                        completion={"asset": {"assetId": asset_id}})

    def operation_cancel(self, operation):
        self.calls.append(("operation_cancel", operation))

    def drain_events(self):
        while self.queue:
            yield self.queue.pop(0)

    def wait(self, operation, timeout=None, on_event=None, interval=0.0):
        while self.queue:
            event = self.queue.pop(0)
            if event.operation == operation and event.is_terminal:
                if event.is_completed:
                    return event.payload
                raise pyoc.OperationFailed(event.status or pyoc.OC_INTERNAL_ERROR, event.message, operation, json.loads(event.raw))
            if on_event is not None:
                on_event(event)
        raise pyoc.Timeout(f"operation {operation} has no terminal event queued")


def _client(**kwargs) -> tuple:
    fake_holder = {}

    def factory(server, identity):
        fake_holder["fake"] = FakePyocClient(server, identity)
        return fake_holder["fake"]

    client = embedded.EmbeddedBridgeClient("https://engine.example", "https://id.example", client_factory=factory, **kwargs)
    return client, fake_holder["fake"]


def _signed_in_client(**kwargs):
    client, fake = _client(**kwargs)
    client.begin_sign_in()
    # the browser flow completes: the login operation is the pending one
    login_op = fake.next_operation
    fake.emit(FakeEvent(pyoc.events.OPERATION_COMPLETED, login_op, {}))
    client.get_session_state()  # folds → signed in → connect started
    return client, fake


OPTIONS = {"Format": 1, "Engine": 0, "Samples": 64, "ResolutionX": 320, "ResolutionY": 240, "Denoise": True, "ColorMode": 2, "FilmTransparent": 2, "ColorDepth": 1}
TILES = {"OverlapPx": 8, "BlendMode": 1}
VIDEO = {"FrameRate": 24, "ConstantRateFactor": 23, "Format": 1}
ATTACHMENTS = [{"Kind": "ImageAsset", "PackagingStrategy": "Reference", "BlobId": "blob-2", "OriginalPath": "C:/tex/wood.png"}]


class SessionTests(unittest.TestCase):
    def test_sign_in_folds_login_and_connects(self):
        client, fake = _client()
        started = client.begin_sign_in()
        self.assertTrue(started.started and started.requires_browser)
        self.assertEqual(fake.calls[-1], ("login_browser",))

        state = client.get_session_state()
        self.assertFalse(state.is_signed_in)

        fake.emit(FakeEvent(pyoc.events.OPERATION_COMPLETED, fake.next_operation, {}))
        state = client.get_session_state()
        self.assertTrue(state.is_signed_in)
        self.assertIn(("connect",), fake.calls)

        scopes = client.get_execution_scope_options()
        self.assertTrue(scopes.can_run_on_all_clients)
        self.assertEqual(scopes.groups[0].group_id, GROUP)
        self.assertEqual(scopes.projects[0].assigned_group_name, "Group")
        self.assertTrue(client.get_session_state().can_launch)

    def test_remembered_session_is_tried_before_the_browser(self):
        client, fake = _client(session_store_path=os.path.join(tempfile.gettempdir(), "oc-embedded", "session.bin"))
        self.assertTrue(fake.attached_store.endswith("session.bin"))
        client.begin_sign_in()
        self.assertEqual([c[0] for c in fake.calls][:2], ["credentials_restore", "login_browser"])

    def test_heartbeat_auto_restore_signs_in_without_the_browser(self):
        client, fake = _client(session_store_path=os.path.join(tempfile.gettempdir(), "oc-embedded", "session.bin"))
        fake.restore_succeeds = True

        client.try_restore_session()  # what the heartbeat calls
        state = client.get_session_state()  # folds the restore completion
        self.assertTrue(state.is_signed_in)
        self.assertIn(("connect",), fake.calls)
        self.assertNotIn("login_browser", [c[0] for c in fake.calls])

        started = client.begin_sign_in()
        self.assertFalse(started.requires_browser)
        self.assertEqual(started.message, "Already signed in.")

    def test_auto_restore_runs_once_and_stays_quiet_on_a_fresh_machine(self):
        client, fake = _client(session_store_path=os.path.join(tempfile.gettempdir(), "oc-embedded", "session.bin"))
        client.try_restore_session()
        state = client.get_session_state()
        self.assertFalse(state.is_signed_in)
        self.assertIsNone(state.last_error, "a missing persisted session is the normal fresh state, not an error")
        self.assertTrue(state.needs_interactive_login)
        client.try_restore_session()
        self.assertEqual([c[0] for c in fake.calls].count("credentials_restore"), 1, "one attempt per process")

    def test_sign_in_during_pending_restore_finishes_it_instead_of_the_browser(self):
        client, fake = _client(session_store_path=os.path.join(tempfile.gettempdir(), "oc-embedded", "session.bin"))
        fake.restore_succeeds = True
        client.try_restore_session()
        # The user clicks Sign In before the heartbeat folded the outcome:
        started = client.begin_sign_in()
        # Either the pump already folded the completion ("Already signed in.") or the
        # pending-restore branch finished it ("Session restored.") — never the browser.
        self.assertFalse(started.requires_browser)
        self.assertTrue(client.get_session_state().is_signed_in)
        self.assertNotIn("login_browser", [c[0] for c in fake.calls])

    def test_no_store_means_no_restore_attempt(self):
        client, fake = _client()
        client.try_restore_session()
        self.assertNotIn("credentials_restore", [c[0] for c in fake.calls])

    def test_sign_out_closes_and_logs_out(self):
        client, fake = _signed_in_client()
        client.get_execution_scope_options()
        self.assertTrue(client.sign_out())
        self.assertIn(("close",), fake.calls)
        self.assertIn(("logout",), fake.calls)
        self.assertFalse(client.get_session_state().is_signed_in)

    def test_launch_before_sign_in_is_refused_locally(self):
        client, _ = _client()
        with self.assertRaises(embedded.EmbeddedClientError):
            client.run_render_still("blob-1", 1, OPTIONS)


class LaunchCompositionTests(unittest.TestCase):
    def setUp(self):
        self.client, self.fake = _signed_in_client()

    def request(self):
        return self.fake.requests[-1]

    def test_render_still_composes_scene_frame_options(self):
        response = self.client.run_render_still("blob-1", 12, OPTIONS, ATTACHMENTS, selected_project_id=PROJECT)
        self.assertEqual(response.status, "Submitted")
        self.assertEqual(response.job_id, "job-1")

        request = self.request()
        self.assertEqual(request["script"], "RenderStill")
        self.assertEqual(request["scope"], {"projectId": PROJECT})
        kinds = [p["kind"] for p in request["parameters"]]
        self.assertEqual(kinds, ["document", "int32", "document"])
        scene = request["parameters"][0]
        self.assertEqual(scene["type"], "render.sceneRef@1")
        self.assertEqual(scene["value"]["blendBlobId"], "blob-1")
        self.assertEqual(scene["value"]["attachedFiles"], [{
            "kind": "ImageAsset", "blobId": "blob-2", "originalPath": "C:/tex/wood.png", "relativePath": "", "packagingStrategy": "Reference"}])
        self.assertEqual(request["parameters"][1]["value"], 12)
        options = request["parameters"][2]
        self.assertEqual(options["type"], "render.options@1")
        self.assertEqual(options["value"], {
            "format": "EXR", "engine": "Cycles", "samples": 64, "resolutionX": 320, "resolutionY": 240, "denoise": True,
            "colorMode": "RGBA", "filmTransparent": "Transparent", "colorDepth": "Eight"})

    def test_render_still_tiled_order(self):
        self.client.run_render_still_tiled("blob-1", 3, 2, 4, OPTIONS, TILES, selected_client_group_id=GROUP)
        request = self.request()
        self.assertEqual(request["script"], "RenderStillTiled")
        self.assertEqual(request["scope"], {"clientGroupId": GROUP})
        self.assertEqual([p["kind"] for p in request["parameters"]], ["document", "int32", "int32", "int32", "document", "document"])
        self.assertEqual([p["value"] for p in request["parameters"][1:4]], [3, 2, 4])
        self.assertEqual(request["parameters"][5], {"kind": "document", "type": "render.tileOptions@1", "value": {"overlapPx": 8, "blendMode": "AlphaBlend"}})

    def test_render_frames_and_video_order(self):
        self.client.run_render_frames("blob-1", 1, 10, OPTIONS)
        frames = self.request()
        self.assertEqual(frames["script"], "RenderFrames")
        self.assertNotIn("scope", frames, "no target = all clients")
        self.assertEqual([p["kind"] for p in frames["parameters"]], ["document", "int32", "int32", "document"])

        self.client.run_render_video("blob-1", 1, 10, OPTIONS, VIDEO)
        video = self.request()
        self.assertEqual(video["script"], "RenderVideo")
        self.assertEqual([p["kind"] for p in video["parameters"]], ["document", "int32", "int32", "document", "document"])
        self.assertEqual(video["parameters"][4], {"kind": "document", "type": "render.videoOptions@1",
                                                  "value": {"frameRate": 24, "constantRateFactor": 23, "format": "Mp4H264"}})

    def test_bake_variants_pick_the_engine_script_and_put_bake_before_tile_and_video(self):
        eevee = dict(OPTIONS, Engine=1)
        self.client.run_bake_and_render_still("blob-1", 1, eevee)
        self.assertEqual(self.request()["script"], "BakeAndRenderStillEevee")
        self.assertEqual([p["type"] for p in self.request()["parameters"] if p["kind"] == "document"],
                         ["render.sceneRef@1", "render.options@1", "render.bakeOptions@1"])

        self.client.run_bake_and_render_still_tiled("blob-1", 1, 2, 2, OPTIONS, TILES)
        self.assertEqual(self.request()["script"], "BakeAndRenderStillTiledCycles")
        self.assertEqual([p["type"] for p in self.request()["parameters"] if p["kind"] == "document"],
                         ["render.sceneRef@1", "render.options@1", "render.bakeOptions@1", "render.tileOptions@1"])

        self.client.run_bake_and_render_frames("blob-1", 1, 5, dict(OPTIONS, Engine=2))
        self.assertEqual(self.request()["script"], "BakeAndRenderFramesGreasePencil")

        self.client.run_bake_and_render_video("blob-1", 1, 5, OPTIONS, VIDEO)
        self.assertEqual(self.request()["script"], "BakeAndRenderVideoCycles")
        self.assertEqual([p["type"] for p in self.request()["parameters"] if p["kind"] == "document"],
                         ["render.sceneRef@1", "render.options@1", "render.bakeOptions@1", "render.videoOptions@1"])

    def test_group_and_project_together_is_a_local_error(self):
        with self.assertRaises(embedded.EmbeddedClientError):
            self.client.run_render_still("blob-1", 1, OPTIONS, selected_client_group_id=GROUP, selected_project_id=PROJECT)
        self.assertEqual(self.fake.requests, [])


class ValidateAndPreflightTests(unittest.TestCase):
    def setUp(self):
        self.client, self.fake = _signed_in_client()

    def test_validate_reads_the_string_result(self):
        self.fake.variables["job-1"] = {"schemaVersion": 1, "kind": "string", "value": json.dumps({"IsValid": True, "Issues": [], "Warnings": ["low samples"]})}
        response = self.client.run_render_validate_blend("blob-1", ATTACHMENTS, selected_project_id=PROJECT)
        self.assertTrue(response.completed and response.is_valid)
        self.assertEqual(response.warnings, ["low samples"])
        self.assertEqual(self.fake.requests[0]["script"], "RenderValidateBlend")
        self.assertEqual(self.fake.requests[0]["scope"], {"projectId": PROJECT})
        self.assertIn(("job_get_variable", "job-1", "result"), self.fake.calls)

    def test_preflight_runs_five_scripts_and_folds_the_typed_results(self):
        frames_doc = {"schemaVersion": 1, "kind": "document", "type": "render.preflightFrames@1", "value": {"canRender": True, "issues": [], "warnings": []}}
        tiled_doc = {"schemaVersion": 1, "kind": "document", "type": "render.preflightStillTiled@1", "value": {"canRender": False, "requestedBlendMode": "AlphaBlend", "issues": ["no CPU tiles"], "warnings": []}}
        video_doc = {"schemaVersion": 1, "kind": "document", "type": "render.preflightVideo@1", "value": {"canRender": True, "issues": [], "warnings": []}}
        diag_doc = {"schemaVersion": 1, "kind": "document", "type": "render.runtimeDiagnostics@1", "value": {"blenderAvailable": True}}
        self.fake.variables.update({"job-1": diag_doc, "job-2": frames_doc, "job-3": frames_doc, "job-4": tiled_doc, "job-5": video_doc})

        response = self.client.run_render_preflight(1, 1, 10, 2, 2, OPTIONS, TILES, VIDEO, selected_client_group_id=GROUP)

        self.assertTrue(response.completed)
        self.assertEqual([r["script"] for r in self.fake.requests],
                         ["RenderRuntimeDiagnostics", "RenderPreflightStill", "RenderPreflightFrames", "RenderPreflightStillTiled", "RenderPreflightVideo"])
        self.assertTrue(all(r.get("scope") == {"clientGroupId": GROUP} for r in self.fake.requests))
        self.assertEqual([p["kind"] for p in self.fake.requests[1]["parameters"]], ["int32", "document"])
        self.assertEqual([p["kind"] for p in self.fake.requests[3]["parameters"]], ["int32", "int32", "document", "document"])
        result = response.result
        self.assertTrue(result.still.can_render)
        self.assertFalse(result.still_tiled.can_render)
        self.assertEqual(result.still_tiled.requested_blend_mode, 1)
        self.assertEqual(result.still_tiled.issues, ["no CPU tiles"])
        self.assertFalse(result.can_render_all)


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.client, self.fake = _signed_in_client()

    def test_blocking_upload_returns_the_asset(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".blend") as handle:
            handle.write(b"x" * 20)
        try:
            response = self.client.upload_blend(handle.name)
        finally:
            os.unlink(handle.name)
        self.assertTrue(response.uploaded)
        self.assertEqual(response.blob_id, "asset-1")
        self.assertEqual(response.file_size, 20)

    def test_background_upload_status_and_cancel(self):
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(b"x" * 20)
        try:
            status = self.client.start_upload_file(handle.name)
        finally:
            os.unlink(handle.name)
        self.assertEqual(status.status, "InProgress")
        self.assertTrue(self.client.cancel_upload(status.transfer_id))
        self.assertIn(("operation_cancel", int(status.transfer_id)), self.fake.calls)

    def test_download_result_lands_under_the_job_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            client, fake = _signed_in_client(download_directory=directory)
            fake.variables["job-7"] = {"kind": "uuid", "value": "res-1"}
            fake.assets["res-1"] = {"assetId": "res-1", "fileName": "still.png", "size": 3}
            response = client.download_result("job-7")
            self.assertTrue(response.downloaded)
            self.assertEqual(response.file_name, "still.png")
            self.assertTrue(response.local_path.startswith(os.path.join(directory, "job-7")))
            self.assertTrue(os.path.isfile(response.local_path))
            self.assertFalse(os.path.exists(response.local_path + ".partial"))
            self.assertEqual(len(response.items), 1)
            status = client.get_download_result_status("job-7")
            self.assertEqual((status.status, status.item_count, status.items_completed, status.progress), ("Completed", 1, 1, 1.0))
            self.assertIs(status.result, response)
            self.assertNotIn("job_download_result", [c[0] for c in fake.calls], "results go asset by asset, from the manifest")

    def test_frame_set_downloads_every_asset_of_the_manifest_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            client, fake = _signed_in_client(download_directory=directory)
            fake.variables["job-8"] = {"kind": "list", "itemKind": "uuid", "value": ["f-1", None, "f-2", "f-3"]}
            fake.assets["f-1"] = {"assetId": "f-1", "fileName": "frame_0001.png", "size": 4}
            fake.assets["f-2"] = {"assetId": "f-2", "fileName": "frame_0002.png", "size": 5}
            fake.assets["f-3"] = {"assetId": "f-3", "fileName": "frame_0002.png", "size": 6}  # a name clash stays distinct on disk

            job = client.get_job("job-8")
            self.assertEqual(job.result_blob_ids, ["f-1", "f-2", "f-3"], "the manifest skips null slots")
            self.assertIsNone(job.result_blob_id, "the single-id field is for single-asset results only")

            started = client.start_download_result("job-8")
            self.assertEqual((started.status, started.item_count, started.total_bytes), ("InProgress", 3, 15))
            self.assertEqual(started.current_file_name, "frame_0001.png")

            response = client.download_result("job-8")
            self.assertEqual([item.file_name for item in response.items], ["frame_0001.png", "frame_0002.png", "frame_0002 (1).png"])
            self.assertTrue(all(os.path.isfile(item.local_path) for item in response.items))
            self.assertEqual([os.path.getsize(item.local_path) for item in response.items], [4, 5, 6])
            self.assertEqual(response.file_name, "frame_0001.png")
            self.assertIn("3 files", response.message)

            downloads = [c for c in fake.calls if c[0] == "asset_download_file"]
            self.assertEqual([c[1] for c in downloads], ["f-1", "f-2", "f-3"], "one after another, in frame order")
            self.assertTrue(all(c[2].endswith(".partial") for c in downloads), "staged as .partial until complete")

            status = client.get_download_result_status("job-8")
            self.assertEqual((status.items_completed, status.downloaded_bytes, status.progress), (3, 15, 1.0))

    def test_get_job_maps_the_job_document(self):
        job = self.client.get_job("job-9")
        self.assertEqual(job.status, "Completed")
        self.assertTrue(job.is_completed)
        self.assertEqual(job.overall_progress, 1.0)
        self.assertEqual(job.result_blob_ids, [], "no stored result yet: the panel shows 'finalizing' and polls on")
        self.assertTrue(self.client.cancel_job("job-9"))

    def test_get_job_resolves_the_result_once_the_server_stored_it(self):
        self.fake.variable_errors["job-10"] = "Job is not running and has no stored result"
        self.assertEqual(self.client.get_job("job-10").result_blob_id, None)
        del self.fake.variable_errors["job-10"]
        self.fake.variables["job-10"] = {"kind": "uuid", "value": "res-9"}
        job = self.client.get_job("job-10")
        self.assertEqual((job.result_blob_id, job.result_blob_ids), ("res-9", ["res-9"]))
        reads = [c for c in self.fake.calls if c[0] == "job_get_variable"]
        self.client.get_job("job-10")
        self.assertEqual(len([c for c in self.fake.calls if c[0] == "job_get_variable"]), len(reads), "the manifest is read once")

    def test_get_job_names_a_server_that_cannot_describe_the_result(self):
        self.fake.variable_errors["job-11"] = "The variable's type is not published as a document contract"
        with self.assertRaises(embedded.EmbeddedClientError) as raised:
            self.client.get_job("job-11")
        self.assertIn("1.6.79", str(raised.exception))

    def test_running_jobs_do_not_read_the_result(self):
        self.fake.job_status = "Processing"
        job = self.client.get_job("job-12")
        self.assertEqual((job.status, job.is_completed, job.result_blob_ids), ("Processing", False, []))
        self.assertNotIn("job_get_variable", [c[0] for c in self.fake.calls])


class RenderSettingsTests(unittest.TestCase):
    def test_settings_round_trip_through_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            client, _ = _client(settings_path=os.path.join(directory, "render-settings.json"))
            self.assertEqual(client.get_render_settings().tiles_x, 2)
            payload = bridge_models.RenderSettingsResponse(tiles_x=4, video_crf=18, last_group_id="p:p1").to_payload()
            self.assertTrue(client.set_render_settings(payload))
            loaded = client.get_render_settings()
            self.assertEqual((loaded.tiles_x, loaded.video_crf, loaded.last_group_id), (4, 18, "p:p1"))


if __name__ == "__main__":
    unittest.main()
