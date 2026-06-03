# Tier B — local in-process controller tests

> **STATUS: IMPLEMENTED + VERIFIED (2026-06-03)** in the sibling project
> `OutWit.Render.BlenderBridge.LocalTests`. Three tests run REAL in-process Blender renders
> (ValidateBlend / RenderStill / RenderFrames) and pass, confirming the full chain and the
> `GetResultAsync<T>` conversion for string / Guid / collection results. The notes below are the
> original design; one addition learned during implementation:
>
> - The Render controller declares runtime `[WitPluginDependency]` on the **Variables** and **Grid**
>   controllers, so `OutWit.Controller.Variables` + `OutWit.Controller.Grid` must ALSO be referenced
>   (their modules stage next to `render.module`), or `WitEngineNodeSdk.Reload` throws
>   "Plugin 'Render' has an unresolved dependency on 'Variables'".

## Design (all facts verified)

Two test tiers for the Blender bridge:

- **Tier A (live)** — `BridgeRestLiveIntegrationTests`, `[Explicit]` + env-gated
  (`OMNIBUSCLOUD_API_KEY`). Bridge → `WitCloudClient` (apikey) → real
  `engine.omnibuscloud.com`. Exercises wire + auth + server + real distribution.
  Already wired (`BridgeLiveCloudConnectionService`).
- **Tier B (local)** — run the **real render controller in-process** via the public
  `OutWit.Engine.Sdk`, with no WitCloud server, no online clients, no deploy cycle.
  Designed + proven below; **not yet implemented**.

## Why it works (verified 2026-06-03)

- `OutWit.Engine.Sdk` (nuget.org, 1.1.4) is a public in-process script runner.
  Its only deps are public: `OutWit.Engine.Parser`, `OutWit.Engine.Shared`,
  `OutWit.Common.Logging`, `OutWit.Common.Plugins`. **No closed `OutWit.Engine`.**
- Referencing `OutWit.Controller.Render` (1.16.0) stages the controller module
  (activities + `controller.json` + DLLs) into `bin/.../@Controllers/render.module/`
  via its `build/.targets`, and its asset resolver fetches Blender/FFmpeg into
  `render.module/blender/<os>/` + `render.module/ffmpeg/<os>/`.
- Referencing `OutWit.Controller.Render.Scripts` (1.0.1) stages the 32 bundled
  `.wit` scripts into `bin/.../@Scripts/*.wit` (flat, no Config sub-folder).
- The controller's `RenderBinaryResolver` finds Blender at the staged module path,
  so a Tier-B render needs **no** `@Prerequisites/` — Blender comes from the package.

## Engine.Sdk run API (from the controller's own RenderProductionScript* tests)

```csharp
WitEngineNodeSdk.Instance.Reload(useIsolatedContext: false, moduleFolder: controllersDir,
    configureServices: s => s.AddSingleton<IWitBlobService>(blobService));
var engine = WitEngineSdk.Instance;
engine.Reload(useIsolatedContext: false, logger: null, moduleFolder: controllersDir,
    configureServices: s => {
        s.AddSingleton<IWitBlobService>(blobService);
        s.AddSingleton<IWitNodesManager>(new RenderTestNodesManager(WitEngineNodeSdk.Instance));
    });

var job = engine.Compile(witScriptText);                  // parse only — no Blender needed
var status = await engine.ScheduleAndWaitAsync(job, p1, p2, ...);  // runs to completion (sync wait)
// status.Result == WitProcessingResult.Completed
var raw = job.Variables["result"].Value;                  // string (JSON) | Guid | Guid[] depending on script
```

- `controllersDir` = `Path.Combine(AppContext.BaseDirectory, "@Controllers")`
  (the dir that *contains* `render.module`).
- scriptsDir = `Path.Combine(AppContext.BaseDirectory, "@Scripts")`.
- scriptName → file is **identity**: `RenderStillCycles` → `@Scripts/RenderStillCycles.wit`.

## `.wit` Job signatures = the bridge's positional param order (identity names)

| Script (scriptName)              | params (order)                                            |
|----------------------------------|----------------------------------------------------------|
| `RenderValidateBlend`            | `(RenderSceneRef scene)`                                  |
| `RenderStill{Cycles,Eevee,GreasePencil}` | `(scene, Int frame, RenderOptions options)`      |
| `RenderStillTiled{…}`            | `(scene, frame, Int tilesX, Int tilesY, options, TileOptions)` |
| `RenderFrames{…}`                | `(scene, Int start, Int end, options)`                   |
| `RenderVideo{…}`                 | `(scene, start, end, options, VideoOptions)`             |

These match exactly the bridge's `client.Scripts.RunAsync(scriptName, …)` arities
(1 / 3 / 6 / 4 / 5 params) in `BridgeRenderLaunchService`.

## `LocalEngineWitCloudClient : IWitCloudClient` (the "public mock-runner")

The bridge only uses: root `GetExecutionScopeOptionsAsync`; `Jobs.GetStatusAsync` +
`Jobs.GetResultAsync<T>`; `Blobs.UploadBlobFromFileAsync` / `GetBlobInfoAsync` /
`DownloadBlobAsync`; `Scripts.RunAsync` (1/3/4/5/6 params); `WitJobHandle.WaitAsync<T>`.
Implement those; everything else throws `NotSupportedException`.

- **Blobs** — back by the shared `RenderTestBlobService` (same instance injected into the
  engine). `UploadBlobFromFileAsync(path)` → `RegisterExistingFile`/`UploadFileAsync` → Guid;
  `DownloadBlobAsync(id)` → read `GetLocalPathAsync(id)`; `GetBlobInfoAsync` → `BlobInfo`.
- **Scripts.RunAsync** — funnel every used overload to one
  `RunCore(scriptName, object?[] values)`: read `@Scripts/{scriptName}.wit` →
  `engine.Compile` → `engine.ScheduleAndWaitAsync(job, values)` → store the completed
  `WitJob` under a new `jobId` → return a `WitJobHandle`.
  **`WitJobHandle`'s ctor is `internal`** → construct via reflection
  `(Guid jobId, string scriptName, IWitCloudJobs jobs)`.
- **Jobs.GetStatusAsync(jobId)** → `ProcessingJobInfo { Status = Completed, OverallProgress = 1.0 }`
  (jobs run synchronously, so always terminal). `GetResultAsync<T>(jobId, var)` → convert
  `job.Variables[var].Value`: `raw is T t ? t` else JSON round-trip
  (`JsonSerializer.Deserialize<T>(raw as string ?? Serialize(raw))`). Mirror the bridge's
  multi-type probe in `BridgeJobQueryService` — **verify the engine variable runtime types
  for Blob (Guid?) and collection (Guid[]/RenderResultCollection) results against a real run.**
- `WitJobHandle.WaitAsync<T>` then "just works": it polls the supplied `IWitCloudJobs`
  (Completed on first poll) and calls `GetResultAsync<T>`.

## Doubles to copy from the controller test project (all on public Engine.Interfaces)

`RenderTestNodesManager : IWitNodesManager`, `RenderTestActivityNode : IWitEngineActivityNode`,
`RenderTestBlobService : IWitBlobService`. **Do not** copy `RenderTestAssetPaths` verbatim —
its `FindControllersPath` looks for `@Controllers/Debug` (controller-repo staging). For the
nuget consumer layout use `AppContext.BaseDirectory/@Controllers` + `/@Scripts` directly.

## Isolation — keep the default build lean (IMPORTANT)

Referencing `OutWit.Controller.Render` fetches **~3.6 GB of per-platform Blender** (the
controller's `ResolveForAllPlatforms="true"`) into the bin on every build — unacceptable for
CI / the green baseline. So Tier B must live in a **separate, opt-in project**
(`OutWit.Render.BlenderBridge.LocalTests`) that carries the four controller/engine package
refs, so the main `*.Tests` project (CI green: pure-local + Tier A `[Explicit]`) stays lean.
Tier-B render tests `Assert.Ignore` when the host Blender is absent.

Tests mirror `BridgeRestLiveIntegrationTests` bodies (upload → run → wait → download → assert
a real PNG/MP4), but inject a `LocalEngineWitCloudClient`-backed `IBridgeCloudConnectionService`
into `BridgeLocalHost` instead of the live apikey one.
