using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Controller.Render.Model;

namespace OutWit.Render.BlenderBridge.Channels.Interfaces
{
    /// <summary>
    /// Local addon-facing WitRPC channel exposed by the Blender bridge.
    /// </summary>
    public interface IBlenderBridgeChannel
    {
        /// <summary>
        /// Returns bridge health and session summary information.
        /// </summary>
        Task<BridgeStatusResponse> GetBridgeStatusAsync();

        /// <summary>
        /// Begins interactive sign-in for the bridge user session.
        /// </summary>
        Task<BeginSignInResponse> BeginSignInAsync();

        /// <summary>
        /// Signs the current bridge session out.
        /// </summary>
        Task<bool> SignOutAsync();

        /// <summary>
        /// Returns the current session state.
        /// </summary>
        Task<SessionStateResponse> GetSessionStateAsync();

        /// <summary>
        /// Returns execution scope options available to the current user session.
        /// </summary>
        Task<ExecutionScopeOptionsResponse> GetExecutionScopeOptionsAsync();

        /// <summary>
        /// Acquires or refreshes the local addon lease for this bridge process.
        /// </summary>
        Task<AcquireLeaseResponse> AcquireLeaseAsync(int ownerProcessId, string leaseId, string? addonVersion = null);

        /// <summary>
        /// Refreshes the heartbeat for the local addon lease.
        /// </summary>
        Task<bool> PingLeaseAsync(string leaseId);

        /// <summary>
        /// Releases the local addon lease.
        /// </summary>
        Task<bool> ReleaseLeaseAsync(string leaseId);

        /// <summary>
        /// Uploads a local Blender scene file into cloud blob storage.
        /// </summary>
        Task<UploadBlendResponse> UploadBlendAsync(string filePath);

        /// <summary>
        /// Uploads one local dependency artifact into cloud blob storage.
        /// </summary>
        Task<UploadBlendResponse> UploadFileAsync(string filePath);

        /// <summary>
        /// Runs the bundled RenderValidateBlend script for one uploaded scene blob.
        /// </summary>
        Task<RenderValidateBlendResponse> RunRenderValidateBlendAsync(Guid sceneBlobId);

        /// <summary>
        /// Runs the bundled RenderValidateBlend script for one uploaded scene blob with addon-provided attachment metadata.
        /// </summary>
        Task<RenderValidateBlendResponse> RunRenderValidateBlendAsync(Guid sceneBlobId, List<RenderSceneAttachmentRefData> attachedFiles);

        /// <summary>
        /// Runs the bundled render preflight diagnostics for the current packaged runtime.
        /// </summary>
        Task<RenderPreflightResponse> RunRenderPreflightAsync(
            int frame,
            int startFrame,
            int endFrame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            VideoOptionsData video);

        /// <summary>
        /// Launches the bundled RenderStill script.
        /// </summary>
        Task<RunRenderStillResponse> RunRenderStillAsync(Guid sceneBlobId, int frame, RenderOptionsData options);

        /// <summary>
        /// Launches the bundled RenderStill script with addon-provided attachment metadata.
        /// </summary>
        Task<RunRenderStillResponse> RunRenderStillAsync(Guid sceneBlobId, int frame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles);

        /// <summary>
        /// Launches the bundled RenderStill script targeted at a specific client group (crowdcomputing).
        /// </summary>
        Task<RunRenderStillResponse> RunRenderStillAsync(Guid sceneBlobId, int frame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedClientGroupId);

        /// <summary>
        /// Launches the bundled RenderStillTiled script.
        /// </summary>
        Task<RunRenderStillTiledResponse> RunRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions);

        /// <summary>
        /// Launches the bundled RenderStillTiled script with addon-provided attachment metadata.
        /// </summary>
        Task<RunRenderStillTiledResponse> RunRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            List<RenderSceneAttachmentRefData> attachedFiles);

        /// <summary>
        /// Launches the bundled RenderStillTiled script targeted at a specific client group (crowdcomputing).
        /// </summary>
        Task<RunRenderStillTiledResponse> RunRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            List<RenderSceneAttachmentRefData> attachedFiles,
            Guid selectedClientGroupId);

        /// <summary>
        /// Launches the bundled RenderFrames script.
        /// </summary>
        Task<RunRenderFramesResponse> RunRenderFramesAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options);

        /// <summary>
        /// Launches the bundled RenderFrames script with addon-provided attachment metadata.
        /// </summary>
        Task<RunRenderFramesResponse> RunRenderFramesAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles);

        /// <summary>
        /// Launches the bundled RenderFrames script targeted at a specific client group (crowdcomputing).
        /// </summary>
        Task<RunRenderFramesResponse> RunRenderFramesAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedClientGroupId);

        /// <summary>
        /// Launches the bundled RenderVideo script.
        /// </summary>
        Task<RunRenderVideoResponse> RunRenderVideoAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, VideoOptionsData video);

        /// <summary>
        /// Launches the bundled RenderVideo script with addon-provided attachment metadata.
        /// </summary>
        Task<RunRenderVideoResponse> RunRenderVideoAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, VideoOptionsData video, List<RenderSceneAttachmentRefData> attachedFiles);

        /// <summary>
        /// Launches the bundled RenderVideo script targeted at a specific client group (crowdcomputing).
        /// </summary>
        Task<RunRenderVideoResponse> RunRenderVideoAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, VideoOptionsData video, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedClientGroupId);

        /// <summary>
        /// Launches the bundled BakeAndRenderStill script (delegated simulation bake, then render) with
        /// addon-provided attachment metadata.
        /// </summary>
        Task<RunRenderStillResponse> RunBakeAndRenderStillAsync(Guid sceneBlobId, int frame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles);

        /// <summary>
        /// Launches the bundled BakeAndRenderStill script targeted at a specific client group (crowdcomputing).
        /// </summary>
        Task<RunRenderStillResponse> RunBakeAndRenderStillAsync(Guid sceneBlobId, int frame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedClientGroupId);

        /// <summary>
        /// Launches the bundled BakeAndRenderStillTiled script with addon-provided attachment metadata.
        /// </summary>
        Task<RunRenderStillTiledResponse> RunBakeAndRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            List<RenderSceneAttachmentRefData> attachedFiles);

        /// <summary>
        /// Launches the bundled BakeAndRenderStillTiled script targeted at a specific client group (crowdcomputing).
        /// </summary>
        Task<RunRenderStillTiledResponse> RunBakeAndRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            List<RenderSceneAttachmentRefData> attachedFiles,
            Guid selectedClientGroupId);

        /// <summary>
        /// Launches the bundled BakeAndRenderFrames script with addon-provided attachment metadata.
        /// </summary>
        Task<RunRenderFramesResponse> RunBakeAndRenderFramesAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles);

        /// <summary>
        /// Launches the bundled BakeAndRenderFrames script targeted at a specific client group (crowdcomputing).
        /// </summary>
        Task<RunRenderFramesResponse> RunBakeAndRenderFramesAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedClientGroupId);

        /// <summary>
        /// Launches the bundled BakeAndRenderVideo script with addon-provided attachment metadata.
        /// </summary>
        Task<RunRenderVideoResponse> RunBakeAndRenderVideoAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, VideoOptionsData video, List<RenderSceneAttachmentRefData> attachedFiles);

        /// <summary>
        /// Launches the bundled BakeAndRenderVideo script targeted at a specific client group (crowdcomputing).
        /// </summary>
        Task<RunRenderVideoResponse> RunBakeAndRenderVideoAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, VideoOptionsData video, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedClientGroupId);

        /// <summary>
        /// Returns the current summary of one bridge-launched cloud job.
        /// </summary>
        Task<GetJobResponse> GetJobAsync(Guid jobId);

        /// <summary>
        /// Requests cancellation of one bridge-launched cloud job. Returns true on success.
        /// </summary>
        Task<bool> CancelJobAsync(Guid jobId);

        /// <summary>
        /// Downloads the final result of one bridge-launched job into the local bridge download cache.
        /// </summary>
        Task<DownloadResultResponse> DownloadResultAsync(Guid jobId);

        /// <summary>
        /// Returns the persisted per-user render preferences (sticky "remember last render settings").
        /// </summary>
        Task<RenderSettingsResponse> GetRenderSettingsAsync();

        /// <summary>
        /// Persists the given per-user render preferences snapshot. Returns true on success.
        /// </summary>
        Task<bool> SetRenderSettingsAsync(RenderSettingsResponse renderSettings);
    }
}
