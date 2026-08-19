# How this addon talks to OmnibusCloud — and how to build your own integration

This repository is a working, production-grade example of an OmnibusCloud
**initiator**: an application that signs users in, uploads assets, submits
jobs to the network, follows them, and downloads results. Since 2.0 it does
all of that **in-process** through the OmnibusCloud native SDK — no companion
process, no local REST, no .NET on the user's machine. If you are building an
integration for another host (a DCC, a C++ application, a pipeline tool),
everything below is the template.

## The pieces

```
Blender (Python)
 └─ outwit_render_bridge/            the extension
     ├─ vendor/pyoc/                 the SDK's Python face (ctypes, stdlib-only)
     │   └─ native/<rid>/            omnibuscloud_native — the SDK library per platform
     ├─ vendor/render_documents.py   the Render controller's generated vocabulary binding
     └─ bridge_client_embedded.py    the addon's client: pyoc + documents → panel-shaped state
```

- **`omnibuscloud_native`** (`.dll` / `.so` / `.dylib`) — the OmnibusCloud
  client SDK compiled to a self-contained native library with a C ABI
  (23 exports, `omnibuscloud.h`). It owns the connection (WebSocket to the
  engine), authentication (OIDC browser sign-in with PKCE, or an access
  token you provide), the persisted session (OS keystore: DPAPI / Keychain /
  libsecret — token material never reaches the host language), asset
  transfers with progress, job submission, and an event queue the host polls.
  Distributed as the [`OutWit.Cloud.SDK.Native`](https://www.nuget.org/packages/OutWit.Cloud.SDK.Native)
  package on nuget.org: `runtimes/<rid>/native/` + the C/C++ headers + pyoc.
- **`pyoc`** — a thin, dependency-free Python binding over that ABI: a
  `Client` with one method per entry point, typed errors, an event iterator,
  and a `JobRequest` builder. A C++ host uses `omnibuscloud.hpp` instead;
  any other language binds the C ABI directly.
- **The vocabulary binding** (`render_documents.py`) — generated **from the
  controller's model** (see the [Controllers author guide](https://github.com/OmnibusCloud/Controllers/blob/main/docs/controller-author-guide.md#non-net-initiators-publishing-a-document-vocabulary)),
  vendored here. It gives the host typed dataclasses (`RenderOptions`,
  `RenderSceneRef`, …) that serialize to exactly the wire shape the server
  materializes. A new controller means vendoring a new generated file —
  never rebuilding the native library.

## The flow

1. **Load once per process.** The library is process-lifetime
   (`pyoc.load(path)`); the addon stages it out of the extension directory
   first because Windows locks loaded DLLs (which would break addon updates).
2. **Sign in.** `credentials_attach(store_path)` + a background
   `credentials_restore` at startup silently resurrect a remembered session;
   only a fresh machine sees the browser (`login_browser`). Scopes
   (`scopes_list`) tell the UI which groups/projects the account may target.
3. **Upload the scene.** `asset_upload_file` returns an operation id;
   progress arrives as events; the completion carries the asset id.
4. **Submit a job document.** One JSON document expresses the whole
   submission — script name, scope, positional parameters:

   ```python
   options = render.RenderOptions(engine=render.RenderEngine.Cycles, samples=64)
   scene = render.RenderSceneRef(blend_blob_id=asset_id)
   request = pyoc.JobRequest("RenderStill").params(scene, 1, options).project(project_id)
   operation = client.job_submit(request)
   ```

   The server's *document door* validates the document against the
   vocabulary published by the installed controllers and materializes the
   parameters into the same typed pipeline every .NET initiator uses.
5. **Follow the job.** Poll `job_get`; the completion payload is the job
   document (status, progress, error). `job_cancel` propagates to the nodes.
6. **Read results.** `job_get_variable(job, "result")` returns a *value
   document*: one asset id for a single artifact, or a `list` of ids for a
   frame set (the result manifest). Fetch each with `asset_download_file`;
   typed result objects (`render.preflight@1`, …) come back through
   `render.from_value_document(...)`.

## The event model

The library never calls back into the host: it queues events
(`operation-progress`, `operation-completed`, `operation-failed`,
`connection-state`, `authorization-required`) and the host drains them when
convenient — from a UI timer in Blender's case. That keeps threading trivial
in hosts with strict main-thread rules (most DCCs).

## What the host never does

- Touch tokens, refresh flows, or the keystore — the SDK owns them.
- Serialize wire formats by hand — generated bindings + the door own them.
- Get rebuilt for a new controller — vocabularies are data, shipped by the
  controller's model package (`documents/` in its nupkg).

## History

Through 1.x this addon drove a bundled .NET sidecar over loopback REST — the
process management (spawn/adopt, lease heartbeats, watchdogs, port
conflicts) and its failure modes are exactly what the in-process SDK
deleted. The 1.x line lives in git history (`addon-v1.*` tags).
