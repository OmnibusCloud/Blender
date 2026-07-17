using Microsoft.Extensions.Logging;
using System.Linq;
using System.Text.Json;
using OutWit.Cloud.Data.Processing;
using OutWit.Cloud.SDK;
using OutWit.Cloud.SDK.Scripts;
using OutWit.Controller.Render.Model;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;
using OutWit.Render.BlenderBridge.Services.Hosting.Interfaces;
using OutWit.Render.BlenderBridge.Services.Render.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Render
{
    /// <summary>
    /// Bridge-side bundled render script launch operations, built on the public SDK
    /// (<c>client.Scripts</c>): fire-and-forget launches return a job handle; validate/preflight
    /// submit-and-wait via <see cref="WitJobHandle.WaitAsync{TResult}"/>.
    /// </summary>
    [InjectableHost]
    public partial class BridgeRenderLaunchService : IBridgeRenderLaunchService
    {
        #region Constants

        private static readonly TimeSpan POLL_INTERVAL = TimeSpan.FromMilliseconds(250);
        private static readonly TimeSpan DEFAULT_TIMEOUT = TimeSpan.FromSeconds(30);

        private const string RENDER_VALIDATE_BLEND_SCRIPT = "RenderValidateBlend";
        private const string RENDER_RUNTIME_DIAGNOSTICS_SCRIPT = "RenderRuntimeDiagnostics";
        private const string RENDER_PREFLIGHT_STILL_SCRIPT = "RenderPreflightStill";
        private const string RENDER_PREFLIGHT_FRAMES_SCRIPT = "RenderPreflightFrames";
        private const string RENDER_PREFLIGHT_STILL_TILED_SCRIPT = "RenderPreflightStillTiled";
        private const string RENDER_PREFLIGHT_VIDEO_SCRIPT = "RenderPreflightVideo";
        private const string RENDER_STILL_SCRIPT = "RenderStill";
        private const string RENDER_STILL_CYCLES_SCRIPT = "RenderStillCycles";
        private const string RENDER_STILL_EEVEE_SCRIPT = "RenderStillEevee";
        private const string RENDER_STILL_GREASE_PENCIL_SCRIPT = "RenderStillGreasePencil";
        private const string RENDER_STILL_TILED_SCRIPT = "RenderStillTiled";
        private const string RENDER_STILL_TILED_CYCLES_SCRIPT = "RenderStillTiledCycles";
        private const string RENDER_STILL_TILED_EEVEE_SCRIPT = "RenderStillTiledEevee";
        private const string RENDER_STILL_TILED_GREASE_PENCIL_SCRIPT = "RenderStillTiledGreasePencil";
        private const string RENDER_FRAMES_SCRIPT = "RenderFrames";
        private const string RENDER_FRAMES_CYCLES_SCRIPT = "RenderFramesCycles";
        private const string RENDER_FRAMES_EEVEE_SCRIPT = "RenderFramesEevee";
        private const string RENDER_FRAMES_GREASE_PENCIL_SCRIPT = "RenderFramesGreasePencil";
        private const string RENDER_VIDEO_SCRIPT = "RenderVideo";
        private const string RENDER_VIDEO_CYCLES_SCRIPT = "RenderVideoCycles";
        private const string RENDER_VIDEO_EEVEE_SCRIPT = "RenderVideoEevee";
        private const string RENDER_VIDEO_GREASE_PENCIL_SCRIPT = "RenderVideoGreasePencil";

        // Bake-and-render variants: the controller first delegates a simulation bake to the fastest
        // node (Render.BakeSimulation via Grid.Delegate), then distributes the baked scene exactly
        // like the plain Render* counterparts. There is no engine-agnostic variant — the bake is
        // engine-independent but the per-frame render is not, so every variant is engine-specific.
        private const string BAKE_AND_RENDER_STILL_CYCLES_SCRIPT = "BakeAndRenderStillCycles";
        private const string BAKE_AND_RENDER_STILL_EEVEE_SCRIPT = "BakeAndRenderStillEevee";
        private const string BAKE_AND_RENDER_STILL_GREASE_PENCIL_SCRIPT = "BakeAndRenderStillGreasePencil";
        private const string BAKE_AND_RENDER_STILL_TILED_CYCLES_SCRIPT = "BakeAndRenderStillTiledCycles";
        private const string BAKE_AND_RENDER_STILL_TILED_EEVEE_SCRIPT = "BakeAndRenderStillTiledEevee";
        private const string BAKE_AND_RENDER_STILL_TILED_GREASE_PENCIL_SCRIPT = "BakeAndRenderStillTiledGreasePencil";
        private const string BAKE_AND_RENDER_FRAMES_CYCLES_SCRIPT = "BakeAndRenderFramesCycles";
        private const string BAKE_AND_RENDER_FRAMES_EEVEE_SCRIPT = "BakeAndRenderFramesEevee";
        private const string BAKE_AND_RENDER_FRAMES_GREASE_PENCIL_SCRIPT = "BakeAndRenderFramesGreasePencil";
        private const string BAKE_AND_RENDER_VIDEO_CYCLES_SCRIPT = "BakeAndRenderVideoCycles";
        private const string BAKE_AND_RENDER_VIDEO_EEVEE_SCRIPT = "BakeAndRenderVideoEevee";
        private const string BAKE_AND_RENDER_VIDEO_GREASE_PENCIL_SCRIPT = "BakeAndRenderVideoGreasePencil";

        private static readonly JsonSerializerOptions JSON_OPTIONS = new()
        {
            PropertyNameCaseInsensitive = true
        };

        #endregion

        #region IBridgeRenderLaunchService

        public async Task<RenderValidateBlendResponse> RunRenderValidateBlendAsync(Guid sceneBlobId, CancellationToken cancellationToken = default)
        {
            return await RunRenderValidateBlendAsync(sceneBlobId, null, cancellationToken);
        }

        public async Task<RenderValidateBlendResponse> RunRenderValidateBlendAsync(
            Guid sceneBlobId,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles,
            CancellationToken cancellationToken = default)
        {
            ThrowIfSceneBlobIdMissing(sceneBlobId);

            var client = await GetRequiredClientAsync(cancellationToken);
            var scene = CreateScene(sceneBlobId, attachedFiles);

            using var timeoutSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeoutSource.CancelAfter(DEFAULT_TIMEOUT);

            var handle = await client.Scripts.RunAsync(RENDER_VALIDATE_BLEND_SCRIPT, scene);
            var waited = await handle.WaitAsync<string>("result", pollInterval: POLL_INTERVAL, ct: timeoutSource.Token);

            if (waited.Status == ProcessingJobStatus.Completed)
            {
                var validation = !string.IsNullOrWhiteSpace(waited.Result)
                    ? JsonSerializer.Deserialize<RenderValidateBlendData>(waited.Result, JSON_OPTIONS)
                    : null;

                if (validation == null)
                    throw new InvalidOperationException("Bridge render validate result retrieval failed for the current RenderValidateBlendData JSON contract.");

                Logger.LogInformation("Bridge RenderValidateBlend completed for blob {BlobId} with result {IsValid} in job {JobId}",
                    sceneBlobId,
                    validation.IsValid,
                    handle.JobId);

                return new RenderValidateBlendResponse
                {
                    JobId = handle.JobId,
                    Completed = true,
                    IsValid = validation.IsValid,
                    Issues = [.. validation.Issues],
                    Warnings = [.. validation.Warnings],
                    Status = waited.Status.ToString(),
                    Message = CreateValidationMessage(validation)
                };
            }

            return new RenderValidateBlendResponse
            {
                JobId = handle.JobId,
                Completed = false,
                IsValid = false,
                Status = waited.Status.ToString(),
                Message = waited.ErrorMessage ?? "Blend validation did not complete successfully."
            };
        }

        public async Task<RenderPreflightResponse> RunRenderPreflightAsync(
            int frame,
            int startFrame,
            int endFrame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            VideoOptionsData video,
            CancellationToken cancellationToken = default)
        {
            ArgumentNullException.ThrowIfNull(options);
            ArgumentNullException.ThrowIfNull(tileOptions);
            ArgumentNullException.ThrowIfNull(video);

            var client = await GetRequiredClientAsync(cancellationToken);

            var runtimeDiagnostics = await RunAndGetResultAsync<RenderRuntimeDiagnosticsData>(
                client,
                s => s.RunAsync(RENDER_RUNTIME_DIAGNOSTICS_SCRIPT),
                "Bridge runtime diagnostics",
                cancellationToken);

            Logger.LogDebug(
                "Bridge runtime diagnostics: SelectedRenderBackend={SelectedRenderBackend}, UsesGpuForRendering={UsesGpuForRendering}, AvailableRenderBackends={AvailableRenderBackends}, Message={Message}",
                runtimeDiagnostics.SelectedRenderBackend ?? "none",
                runtimeDiagnostics.UsesGpuForRendering,
                FormatAvailableRenderBackends(runtimeDiagnostics),
                runtimeDiagnostics.RenderBackendSelectionMessage ?? "none");

            var result = new RenderPreflightData
            {
                RuntimeDiagnostics = runtimeDiagnostics,
                Still = await RunAndGetResultAsync<RenderPreflightFramesData>(
                    client,
                    s => s.RunAsync(RENDER_PREFLIGHT_STILL_SCRIPT, frame, options),
                    "Bridge still preflight",
                    cancellationToken),
                Frames = await RunAndGetResultAsync<RenderPreflightFramesData>(
                    client,
                    s => s.RunAsync(RENDER_PREFLIGHT_FRAMES_SCRIPT, startFrame, endFrame, options),
                    "Bridge frame-range preflight",
                    cancellationToken),
                StillTiled = await RunAndGetResultAsync<RenderPreflightStillTiledData>(
                    client,
                    s => s.RunAsync(RENDER_PREFLIGHT_STILL_TILED_SCRIPT, tilesX, tilesY, options, tileOptions),
                    "Bridge tiled-still preflight",
                    cancellationToken),
                Video = await RunAndGetResultAsync<RenderPreflightVideoData>(
                    client,
                    s => s.RunAsync(RENDER_PREFLIGHT_VIDEO_SCRIPT, options, video),
                    "Bridge video preflight",
                    cancellationToken)
            };

            result.CanRenderAll = (result.Still?.CanRender ?? false)
                                  && (result.Frames?.CanRender ?? false)
                                  && (result.StillTiled?.CanRender ?? false)
                                  && (result.Video?.CanRender ?? false);

            if (result.CanRenderAll)
            {
                Logger.LogInformation("Bridge render preflight completed. CanRenderAll={CanRenderAll}", result.CanRenderAll);
            }
            else
            {
                Logger.LogWarning(
                    "Bridge render preflight completed with blocking issues. SelectedRenderBackend={SelectedRenderBackend}, UsesGpuForRendering={UsesGpuForRendering}, BlockingIssueCount={BlockingIssueCount}",
                    runtimeDiagnostics.SelectedRenderBackend ?? "none",
                    runtimeDiagnostics.UsesGpuForRendering,
                    CountIssues(result));
            }

            return new RenderPreflightResponse
            {
                Completed = true,
                Status = ProcessingJobStatus.Completed.ToString(),
                Message = CreatePreflightMessage(result),
                Result = result
            };
        }

        public async Task<RunRenderStillResponse> RunRenderStillAsync(
            Guid sceneBlobId,
            int frame,
            RenderOptionsData options,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            Guid? selectedProjectId = null,
            CancellationToken cancellationToken = default)
        {
            ThrowIfSceneBlobIdMissing(sceneBlobId);

            ArgumentNullException.ThrowIfNull(options);

            var client = await GetRequiredClientAsync(cancellationToken);
            var scene = CreateScene(sceneBlobId, attachedFiles);
            var scriptName = ResolveStillScript(options.Engine);

            var handle = HasScopedTarget(selectedClientGroupId, selectedProjectId)
                ? await client.Scripts.SubmitAsync(scriptName, new object?[] { scene, frame, options }, selectedClientGroupId, selectedProjectId)
                : await client.Scripts.RunAsync(scriptName, scene, frame, options);

            Logger.LogInformation("Bridge RenderStill launched for blob {BlobId} at frame {Frame} with job {JobId}",
                sceneBlobId,
                frame,
                handle.JobId);

            JobTrackerService.TrackJob(handle.JobId);

            return new RunRenderStillResponse
            {
                JobId = handle.JobId,
                Status = ProcessingJobStatus.Pending.ToString(),
                Message = "RenderStill launched successfully."
            };
        }

        public async Task<RunRenderStillTiledResponse> RunRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            Guid? selectedProjectId = null,
            CancellationToken cancellationToken = default)
        {
            ThrowIfSceneBlobIdMissing(sceneBlobId);

            ArgumentNullException.ThrowIfNull(options);
            ArgumentNullException.ThrowIfNull(tileOptions);

            var client = await GetRequiredClientAsync(cancellationToken);
            var scene = CreateScene(sceneBlobId, attachedFiles);
            var scriptName = ResolveStillTiledScript(options.Engine);

            var handle = HasScopedTarget(selectedClientGroupId, selectedProjectId)
                ? await client.Scripts.SubmitAsync(scriptName, new object?[] { scene, frame, tilesX, tilesY, options, tileOptions }, selectedClientGroupId, selectedProjectId)
                : await client.Scripts.RunAsync(scriptName, scene, frame, tilesX, tilesY, options, tileOptions);

            Logger.LogInformation("Bridge RenderStillTiled launched for blob {BlobId} at frame {Frame} with tiles {TilesX}x{TilesY} and job {JobId}",
                sceneBlobId,
                frame,
                tilesX,
                tilesY,
                handle.JobId);

            JobTrackerService.TrackJob(handle.JobId);

            return new RunRenderStillTiledResponse
            {
                JobId = handle.JobId,
                Status = ProcessingJobStatus.Pending.ToString(),
                Message = "RenderStillTiled launched successfully."
            };
        }

        public async Task<RunRenderFramesResponse> RunRenderFramesAsync(
            Guid sceneBlobId,
            int startFrame,
            int endFrame,
            RenderOptionsData options,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            Guid? selectedProjectId = null,
            CancellationToken cancellationToken = default)
        {
            ThrowIfSceneBlobIdMissing(sceneBlobId);

            ArgumentNullException.ThrowIfNull(options);

            var client = await GetRequiredClientAsync(cancellationToken);
            var scene = CreateScene(sceneBlobId, attachedFiles);
            var scriptName = ResolveFramesScript(options.Engine);

            var handle = HasScopedTarget(selectedClientGroupId, selectedProjectId)
                ? await client.Scripts.SubmitAsync(scriptName, new object?[] { scene, startFrame, endFrame, options }, selectedClientGroupId, selectedProjectId)
                : await client.Scripts.RunAsync(scriptName, scene, startFrame, endFrame, options);

            Logger.LogInformation("Bridge RenderFrames launched for blob {BlobId} at range {StartFrame}-{EndFrame} with job {JobId}",
                sceneBlobId,
                startFrame,
                endFrame,
                handle.JobId);

            JobTrackerService.TrackJob(handle.JobId);

            return new RunRenderFramesResponse
            {
                JobId = handle.JobId,
                Status = ProcessingJobStatus.Pending.ToString(),
                Message = "RenderFrames launched successfully."
            };
        }

        public async Task<RunRenderVideoResponse> RunRenderVideoAsync(
            Guid sceneBlobId,
            int startFrame,
            int endFrame,
            RenderOptionsData options,
            VideoOptionsData video,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            Guid? selectedProjectId = null,
            CancellationToken cancellationToken = default)
        {
            ThrowIfSceneBlobIdMissing(sceneBlobId);

            ArgumentNullException.ThrowIfNull(options);
            ArgumentNullException.ThrowIfNull(video);

            var client = await GetRequiredClientAsync(cancellationToken);
            var scene = CreateScene(sceneBlobId, attachedFiles);
            var scriptName = ResolveVideoScript(options.Engine);

            var handle = HasScopedTarget(selectedClientGroupId, selectedProjectId)
                ? await client.Scripts.SubmitAsync(scriptName, new object?[] { scene, startFrame, endFrame, options, video }, selectedClientGroupId, selectedProjectId)
                : await client.Scripts.RunAsync(scriptName, scene, startFrame, endFrame, options, video);

            Logger.LogInformation("Bridge RenderVideo launched for blob {BlobId} at range {StartFrame}-{EndFrame} with job {JobId}",
                sceneBlobId,
                startFrame,
                endFrame,
                handle.JobId);

            JobTrackerService.TrackJob(handle.JobId);

            return new RunRenderVideoResponse
            {
                JobId = handle.JobId,
                Status = ProcessingJobStatus.Pending.ToString(),
                Message = "RenderVideo launched successfully."
            };
        }

        public async Task<RunRenderStillResponse> RunBakeAndRenderStillAsync(
            Guid sceneBlobId,
            int frame,
            RenderOptionsData options,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            Guid? selectedProjectId = null,
            CancellationToken cancellationToken = default)
        {
            ThrowIfSceneBlobIdMissing(sceneBlobId);

            ArgumentNullException.ThrowIfNull(options);

            var client = await GetRequiredClientAsync(cancellationToken);
            var scene = CreateScene(sceneBlobId, attachedFiles);
            var bakeOptions = CreateBakeOptions();
            var scriptName = ResolveBakeAndRenderStillScript(options.Engine);

            var handle = HasScopedTarget(selectedClientGroupId, selectedProjectId)
                ? await client.Scripts.SubmitAsync(scriptName, new object?[] { scene, frame, options, bakeOptions }, selectedClientGroupId, selectedProjectId)
                : await client.Scripts.RunAsync(scriptName, scene, frame, options, bakeOptions);

            Logger.LogInformation("Bridge BakeAndRenderStill launched for blob {BlobId} at frame {Frame} with job {JobId}",
                sceneBlobId,
                frame,
                handle.JobId);

            JobTrackerService.TrackJob(handle.JobId);

            return new RunRenderStillResponse
            {
                JobId = handle.JobId,
                Status = ProcessingJobStatus.Pending.ToString(),
                Message = "BakeAndRenderStill launched successfully."
            };
        }

        public async Task<RunRenderStillTiledResponse> RunBakeAndRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            Guid? selectedProjectId = null,
            CancellationToken cancellationToken = default)
        {
            ThrowIfSceneBlobIdMissing(sceneBlobId);

            ArgumentNullException.ThrowIfNull(options);
            ArgumentNullException.ThrowIfNull(tileOptions);

            var client = await GetRequiredClientAsync(cancellationToken);
            var scene = CreateScene(sceneBlobId, attachedFiles);
            var bakeOptions = CreateBakeOptions();
            var scriptName = ResolveBakeAndRenderStillTiledScript(options.Engine);

            // Arg order matches the .wit signature: (scene, frame, tilesX, tilesY, options, bakeOptions, tileOptions).
            var handle = HasScopedTarget(selectedClientGroupId, selectedProjectId)
                ? await client.Scripts.SubmitAsync(scriptName, new object?[] { scene, frame, tilesX, tilesY, options, bakeOptions, tileOptions }, selectedClientGroupId, selectedProjectId)
                : await client.Scripts.RunAsync(scriptName, scene, frame, tilesX, tilesY, options, bakeOptions, tileOptions);

            Logger.LogInformation("Bridge BakeAndRenderStillTiled launched for blob {BlobId} at frame {Frame} with tiles {TilesX}x{TilesY} and job {JobId}",
                sceneBlobId,
                frame,
                tilesX,
                tilesY,
                handle.JobId);

            JobTrackerService.TrackJob(handle.JobId);

            return new RunRenderStillTiledResponse
            {
                JobId = handle.JobId,
                Status = ProcessingJobStatus.Pending.ToString(),
                Message = "BakeAndRenderStillTiled launched successfully."
            };
        }

        public async Task<RunRenderFramesResponse> RunBakeAndRenderFramesAsync(
            Guid sceneBlobId,
            int startFrame,
            int endFrame,
            RenderOptionsData options,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            Guid? selectedProjectId = null,
            CancellationToken cancellationToken = default)
        {
            ThrowIfSceneBlobIdMissing(sceneBlobId);

            ArgumentNullException.ThrowIfNull(options);

            var client = await GetRequiredClientAsync(cancellationToken);
            var scene = CreateScene(sceneBlobId, attachedFiles);
            var bakeOptions = CreateBakeOptions();
            var scriptName = ResolveBakeAndRenderFramesScript(options.Engine);

            var handle = HasScopedTarget(selectedClientGroupId, selectedProjectId)
                ? await client.Scripts.SubmitAsync(scriptName, new object?[] { scene, startFrame, endFrame, options, bakeOptions }, selectedClientGroupId, selectedProjectId)
                : await client.Scripts.RunAsync(scriptName, scene, startFrame, endFrame, options, bakeOptions);

            Logger.LogInformation("Bridge BakeAndRenderFrames launched for blob {BlobId} at range {StartFrame}-{EndFrame} with job {JobId}",
                sceneBlobId,
                startFrame,
                endFrame,
                handle.JobId);

            JobTrackerService.TrackJob(handle.JobId);

            return new RunRenderFramesResponse
            {
                JobId = handle.JobId,
                Status = ProcessingJobStatus.Pending.ToString(),
                Message = "BakeAndRenderFrames launched successfully."
            };
        }

        public async Task<RunRenderVideoResponse> RunBakeAndRenderVideoAsync(
            Guid sceneBlobId,
            int startFrame,
            int endFrame,
            RenderOptionsData options,
            VideoOptionsData video,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            Guid? selectedProjectId = null,
            CancellationToken cancellationToken = default)
        {
            ThrowIfSceneBlobIdMissing(sceneBlobId);

            ArgumentNullException.ThrowIfNull(options);
            ArgumentNullException.ThrowIfNull(video);

            var client = await GetRequiredClientAsync(cancellationToken);
            var scene = CreateScene(sceneBlobId, attachedFiles);
            var bakeOptions = CreateBakeOptions();
            var scriptName = ResolveBakeAndRenderVideoScript(options.Engine);

            // Arg order matches the .wit signature: (scene, startFrame, endFrame, options, bakeOptions, video).
            var handle = HasScopedTarget(selectedClientGroupId, selectedProjectId)
                ? await client.Scripts.SubmitAsync(scriptName, new object?[] { scene, startFrame, endFrame, options, bakeOptions, video }, selectedClientGroupId, selectedProjectId)
                : await client.Scripts.RunAsync(scriptName, scene, startFrame, endFrame, options, bakeOptions, video);

            Logger.LogInformation("Bridge BakeAndRenderVideo launched for blob {BlobId} at range {StartFrame}-{EndFrame} with job {JobId}",
                sceneBlobId,
                startFrame,
                endFrame,
                handle.JobId);

            JobTrackerService.TrackJob(handle.JobId);

            return new RunRenderVideoResponse
            {
                JobId = handle.JobId,
                Status = ProcessingJobStatus.Pending.ToString(),
                Message = "BakeAndRenderVideo launched successfully."
            };
        }

        #endregion

        #region Tools

        private async Task<IWitCloudClient> GetRequiredClientAsync(CancellationToken cancellationToken)
        {
            return await CloudConnectionService.GetClientAsync(cancellationToken)
                   ?? throw new InvalidOperationException("Bridge is not connected to the cloud.");
        }

        // Submit a script and strictly wait for its typed result (used by validate/preflight, which
        // need the value back). Mirrors the bridge's strict 30s-timeout / typed-result contract using
        // the SDK primitives (Scripts.RunAsync + handle.WaitAsync).
        private async Task<T> RunAndGetResultAsync<T>(
            IWitCloudClient client,
            Func<IWitCloudScripts, Task<WitJobHandle>> run,
            string operationName,
            CancellationToken cancellationToken)
        {
            using var timeoutSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeoutSource.CancelAfter(DEFAULT_TIMEOUT);

            var handle = await run(client.Scripts);
            var waited = await handle.WaitAsync<T>("result", pollInterval: POLL_INTERVAL, ct: timeoutSource.Token);

            if (waited.Status != ProcessingJobStatus.Completed)
                throw new InvalidOperationException($"{operationName} did not complete successfully: {waited.ErrorMessage}");

            if (waited.Result == null)
                throw new InvalidOperationException($"{operationName} result retrieval failed.");

            return waited.Result;
        }

        private static RenderSceneRefData CreateScene(Guid sceneBlobId, IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles)
        {
            return new RenderSceneRefData
            {
                BlendBlobId = sceneBlobId,
                AttachedFiles = attachedFiles?.Select(me => (RenderSceneAttachmentRefData)me.Clone()).ToList() ?? []
            };
        }

        private static void ThrowIfSceneBlobIdMissing(Guid sceneBlobId)
        {
            if (sceneBlobId == Guid.Empty)
                throw new InvalidOperationException("Scene blob id is required.");
        }

        // The engine rejects a submit that names both scopes; failing here keeps the error local and
        // instant instead of a round-trip. No target at all = the unscoped all-clients run.
        private static bool HasScopedTarget(Guid? selectedClientGroupId, Guid? selectedProjectId)
        {
            if (selectedClientGroupId.HasValue && selectedProjectId.HasValue)
                throw new InvalidOperationException("A launch may target a client group or a project, not both.");

            return selectedClientGroupId.HasValue || selectedProjectId.HasValue;
        }

        private static string FormatAvailableRenderBackends(RenderRuntimeDiagnosticsData runtimeDiagnostics)
        {
            return runtimeDiagnostics.AvailableRenderBackends.Length == 0
                ? "none"
                : string.Join(",", runtimeDiagnostics.AvailableRenderBackends);
        }

        private static string ResolveStillScript(RenderEngine engine)
        {
            return engine switch
            {
                RenderEngine.Cycles => RENDER_STILL_CYCLES_SCRIPT,
                RenderEngine.Eevee => RENDER_STILL_EEVEE_SCRIPT,
                RenderEngine.GreasePencil => RENDER_STILL_GREASE_PENCIL_SCRIPT,
                _ => RENDER_STILL_SCRIPT
            };
        }

        private static string ResolveFramesScript(RenderEngine engine)
        {
            return engine switch
            {
                RenderEngine.Cycles => RENDER_FRAMES_CYCLES_SCRIPT,
                RenderEngine.Eevee => RENDER_FRAMES_EEVEE_SCRIPT,
                RenderEngine.GreasePencil => RENDER_FRAMES_GREASE_PENCIL_SCRIPT,
                _ => RENDER_FRAMES_SCRIPT
            };
        }

        private static string ResolveStillTiledScript(RenderEngine engine)
        {
            return engine switch
            {
                RenderEngine.Cycles => RENDER_STILL_TILED_CYCLES_SCRIPT,
                RenderEngine.Eevee => RENDER_STILL_TILED_EEVEE_SCRIPT,
                RenderEngine.GreasePencil => RENDER_STILL_TILED_GREASE_PENCIL_SCRIPT,
                _ => RENDER_STILL_TILED_SCRIPT
            };
        }

        private static string ResolveVideoScript(RenderEngine engine)
        {
            return engine switch
            {
                RenderEngine.Cycles => RENDER_VIDEO_CYCLES_SCRIPT,
                RenderEngine.Eevee => RENDER_VIDEO_EEVEE_SCRIPT,
                RenderEngine.GreasePencil => RENDER_VIDEO_GREASE_PENCIL_SCRIPT,
                _ => RENDER_VIDEO_SCRIPT
            };
        }

        // Bake-and-render has no engine-agnostic fallback script, so an unexpected engine value maps
        // to Cycles — the RenderOptionsData default and the safe choice for an unbaked simulation.
        private static string ResolveBakeAndRenderStillScript(RenderEngine engine)
        {
            return engine switch
            {
                RenderEngine.Eevee => BAKE_AND_RENDER_STILL_EEVEE_SCRIPT,
                RenderEngine.GreasePencil => BAKE_AND_RENDER_STILL_GREASE_PENCIL_SCRIPT,
                _ => BAKE_AND_RENDER_STILL_CYCLES_SCRIPT
            };
        }

        private static string ResolveBakeAndRenderStillTiledScript(RenderEngine engine)
        {
            return engine switch
            {
                RenderEngine.Eevee => BAKE_AND_RENDER_STILL_TILED_EEVEE_SCRIPT,
                RenderEngine.GreasePencil => BAKE_AND_RENDER_STILL_TILED_GREASE_PENCIL_SCRIPT,
                _ => BAKE_AND_RENDER_STILL_TILED_CYCLES_SCRIPT
            };
        }

        private static string ResolveBakeAndRenderFramesScript(RenderEngine engine)
        {
            return engine switch
            {
                RenderEngine.Eevee => BAKE_AND_RENDER_FRAMES_EEVEE_SCRIPT,
                RenderEngine.GreasePencil => BAKE_AND_RENDER_FRAMES_GREASE_PENCIL_SCRIPT,
                _ => BAKE_AND_RENDER_FRAMES_CYCLES_SCRIPT
            };
        }

        private static string ResolveBakeAndRenderVideoScript(RenderEngine engine)
        {
            return engine switch
            {
                RenderEngine.Eevee => BAKE_AND_RENDER_VIDEO_EEVEE_SCRIPT,
                RenderEngine.GreasePencil => BAKE_AND_RENDER_VIDEO_GREASE_PENCIL_SCRIPT,
                _ => BAKE_AND_RENDER_VIDEO_CYCLES_SCRIPT
            };
        }

        // Delegated-bake options. The controller bakes every sequential simulation it finds and only
        // reads ResolutionMax (0 = keep the scene's domain resolution); SimulationKinds/CacheFormat
        // are forward-looking metadata. The artist has no knobs for these yet, so defaults are used.
        private static RenderBakeOptionsData CreateBakeOptions()
        {
            return new RenderBakeOptionsData();
        }

        private static int CountIssues(RenderPreflightData result)
        {
            return (result.Still?.Issues.Count ?? 0)
                   + (result.Frames?.Issues.Count ?? 0)
                   + (result.StillTiled?.Issues.Count ?? 0)
                   + (result.Video?.Issues.Count ?? 0);
        }

        private static int CountWarnings(RenderPreflightData result)
        {
            return (result.Still?.Warnings.Count ?? 0)
                   + (result.Frames?.Warnings.Count ?? 0)
                   + (result.StillTiled?.Warnings.Count ?? 0)
                   + (result.Video?.Warnings.Count ?? 0);
        }

        private static string CreateValidationMessage(RenderValidateBlendData validation)
        {
            ArgumentNullException.ThrowIfNull(validation);

            if (!validation.IsValid)
            {
                return validation.Issues.Count > 0
                    ? AppendFinding("Blend validation blocked.", validation.Issues.FirstOrDefault(), validation.Issues.Count)
                    : "Blend validation failed.";
            }

            if (validation.Warnings.Count > 0)
                return AppendFinding("Blend validated with warnings.", validation.Warnings.FirstOrDefault(), validation.Warnings.Count);

            return "Blend validated successfully.";
        }

        private static string CreatePreflightMessage(RenderPreflightData result)
        {
            ArgumentNullException.ThrowIfNull(result);

            if (!result.CanRenderAll)
                return AppendFinding("Render preflight completed with blocking issues.", FirstIssue(result), CountIssues(result));

            if (CountWarnings(result) > 0)
                return AppendFinding("Render preflight completed with warnings.", FirstWarning(result), CountWarnings(result));

            return "Render preflight completed successfully.";
        }

        private static string? FirstIssue(RenderPreflightData result)
        {
            return result.Still?.Issues.FirstOrDefault()
                   ?? result.Frames?.Issues.FirstOrDefault()
                   ?? result.StillTiled?.Issues.FirstOrDefault()
                   ?? result.Video?.Issues.FirstOrDefault();
        }

        private static string? FirstWarning(RenderPreflightData result)
        {
            return result.Still?.Warnings.FirstOrDefault()
                   ?? result.Frames?.Warnings.FirstOrDefault()
                   ?? result.StillTiled?.Warnings.FirstOrDefault()
                   ?? result.Video?.Warnings.FirstOrDefault();
        }

        private static string AppendFinding(string prefix, string? finding, int totalCount)
        {
            if (string.IsNullOrWhiteSpace(finding))
                return prefix;

            return totalCount > 1
                ? $"{prefix} {finding} (+{totalCount - 1} more)"
                : $"{prefix} {finding}";
        }

        #endregion

        #region Properties

        [Inject]
        public IBridgeCloudConnectionService CloudConnectionService { get; set; } = null!;

        [Inject]
        public IBridgeJobTrackerService JobTrackerService { get; set; } = null!;

        [Inject]
        public ILogger<BridgeRenderLaunchService> Logger { get; set; } = null!;

        #endregion
    }
}
