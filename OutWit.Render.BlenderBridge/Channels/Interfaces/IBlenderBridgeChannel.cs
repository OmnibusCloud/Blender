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
        /// Uploads a local Blender scene file into cloud blob storage. Blocks until the transfer
        /// finishes — prefer <see cref="StartUploadBlendAsync"/> + <see cref="GetUploadStatusAsync"/>
        /// for large files.
        /// </summary>
        Task<UploadBlendResponse> UploadBlendAsync(string filePath);

        /// <summary>
        /// Uploads one local dependency artifact into cloud blob storage. Blocks until the transfer
        /// finishes — prefer <see cref="StartUploadFileAsync"/> + <see cref="GetUploadStatusAsync"/>
        /// for large files.
        /// </summary>
        Task<UploadBlendResponse> UploadFileAsync(string filePath);

        /// <summary>
        /// Starts the background upload of a local Blender scene file and returns the transfer's
        /// status snapshot (with its transfer id) immediately.
        /// </summary>
        Task<UploadStatusResponse> StartUploadBlendAsync(string filePath);

        /// <summary>
        /// Starts the background upload of one local dependency artifact and returns the transfer's
        /// status snapshot (with its transfer id) immediately.
        /// </summary>
        Task<UploadStatusResponse> StartUploadFileAsync(string filePath);

        /// <summary>
        /// Returns the current status snapshot of one background upload.
        /// </summary>
        Task<UploadStatusResponse> GetUploadStatusAsync(Guid transferId);

        /// <summary>
        /// Requests cancellation of one in-progress background upload. Returns true when an active
        /// transfer was told to cancel.
        /// </summary>
        Task<bool> CancelUploadAsync(Guid transferId);

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
        /// Validates the blend scoped to the selected render target — utility submits must carry
        /// the same scope as the render, or a non-admin account is rejected ("all clients") before
        /// the render is ever reached. Ids travel as strings ("" = none; both set is an error) so
        /// ONE method covers group/project/none without a Guid-arity explosion in the REST binder.
        /// </summary>
        Task<RenderValidateBlendResponse> RunRenderValidateBlendScopedAsync(
            Guid sceneBlobId,
            List<RenderSceneAttachmentRefData> attachedFiles,
            string selectedClientGroupId,
            string selectedProjectId);

        /// <summary>
        /// Runs the render preflight scoped to the selected render target (see
        /// <see cref="RunRenderValidateBlendScopedAsync"/> for the string-id contract).
        /// </summary>
        Task<RenderPreflightResponse> RunRenderPreflightScopedAsync(
            int frame,
            int startFrame,
            int endFrame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            VideoOptionsData video,
            string selectedClientGroupId,
            string selectedProjectId);

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

        // Project-targeted launches (campaigns). The REST processor binds positional calls by METHOD
        // NAME + argument count, so a same-arity Guid overload of the group variants would be
        // ambiguous — each project launch is its own method name.

        /// <summary>
        /// Launches the bundled RenderStill script targeted at a specific project (campaign).
        /// </summary>
        Task<RunRenderStillResponse> RunRenderStillInProjectAsync(Guid sceneBlobId, int frame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedProjectId);

        /// <summary>
        /// Launches the bundled RenderStillTiled script targeted at a specific project (campaign).
        /// </summary>
        Task<RunRenderStillTiledResponse> RunRenderStillTiledInProjectAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            List<RenderSceneAttachmentRefData> attachedFiles,
            Guid selectedProjectId);

        /// <summary>
        /// Launches the bundled RenderFrames script targeted at a specific project (campaign).
        /// </summary>
        Task<RunRenderFramesResponse> RunRenderFramesInProjectAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedProjectId);

        /// <summary>
        /// Launches the bundled RenderVideo script targeted at a specific project (campaign).
        /// </summary>
        Task<RunRenderVideoResponse> RunRenderVideoInProjectAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, VideoOptionsData video, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedProjectId);

        /// <summary>
        /// Launches the bundled BakeAndRenderStill script targeted at a specific project (campaign).
        /// </summary>
        Task<RunRenderStillResponse> RunBakeAndRenderStillInProjectAsync(Guid sceneBlobId, int frame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedProjectId);

        /// <summary>
        /// Launches the bundled BakeAndRenderStillTiled script targeted at a specific project (campaign).
        /// </summary>
        Task<RunRenderStillTiledResponse> RunBakeAndRenderStillTiledInProjectAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            List<RenderSceneAttachmentRefData> attachedFiles,
            Guid selectedProjectId);

        /// <summary>
        /// Launches the bundled BakeAndRenderFrames script targeted at a specific project (campaign).
        /// </summary>
        Task<RunRenderFramesResponse> RunBakeAndRenderFramesInProjectAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedProjectId);

        /// <summary>
        /// Launches the bundled BakeAndRenderVideo script targeted at a specific project (campaign).
        /// </summary>
        Task<RunRenderVideoResponse> RunBakeAndRenderVideoInProjectAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, VideoOptionsData video, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedProjectId);

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
        /// Blocks until the transfer finishes — prefer <see cref="StartDownloadResultAsync"/> +
        /// <see cref="GetDownloadResultStatusAsync"/> for large results.
        /// </summary>
        Task<DownloadResultResponse> DownloadResultAsync(Guid jobId);

        /// <summary>
        /// Starts (or joins) the background download of one job's result and returns the current
        /// status snapshot immediately.
        /// </summary>
        Task<DownloadStatusResponse> StartDownloadResultAsync(Guid jobId);

        /// <summary>
        /// Returns the current status snapshot of one job's background result download.
        /// </summary>
        Task<DownloadStatusResponse> GetDownloadResultStatusAsync(Guid jobId);

        /// <summary>
        /// Requests cancellation of one job's in-progress result download. Returns true when an
        /// active transfer was told to cancel.
        /// </summary>
        Task<bool> CancelDownloadResultAsync(Guid jobId);

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
