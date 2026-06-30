using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Controller.Render.Model;

namespace OutWit.Render.BlenderBridge.Services.Render.Interfaces
{
    /// <summary>
    /// Owns bridge-side bundled render script launch operations.
    /// </summary>
    public interface IBridgeRenderLaunchService
    {
        /// <summary>
        /// Runs the bundled RenderValidateBlend script for one uploaded scene blob.
        /// </summary>
        Task<RenderValidateBlendResponse> RunRenderValidateBlendAsync(
            Guid sceneBlobId,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            CancellationToken cancellationToken = default);

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
            VideoOptionsData video,
            CancellationToken cancellationToken = default);

        /// <summary>
        /// Launches the bundled RenderStill script.
        /// </summary>
        Task<RunRenderStillResponse> RunRenderStillAsync(
            Guid sceneBlobId,
            int frame,
            RenderOptionsData options,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            CancellationToken cancellationToken = default);

        /// <summary>
        /// Launches the bundled RenderStillTiled script.
        /// </summary>
        Task<RunRenderStillTiledResponse> RunRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            CancellationToken cancellationToken = default);

        /// <summary>
        /// Launches the bundled RenderFrames script.
        /// </summary>
        Task<RunRenderFramesResponse> RunRenderFramesAsync(
            Guid sceneBlobId,
            int startFrame,
            int endFrame,
            RenderOptionsData options,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            CancellationToken cancellationToken = default);

        /// <summary>
        /// Launches the bundled RenderVideo script.
        /// </summary>
        Task<RunRenderVideoResponse> RunRenderVideoAsync(
            Guid sceneBlobId,
            int startFrame,
            int endFrame,
            RenderOptionsData options,
            VideoOptionsData video,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            CancellationToken cancellationToken = default);

        /// <summary>
        /// Launches the bundled BakeAndRenderStill script: delegates a simulation bake to the fastest
        /// node, then renders the single baked frame distributed.
        /// </summary>
        Task<RunRenderStillResponse> RunBakeAndRenderStillAsync(
            Guid sceneBlobId,
            int frame,
            RenderOptionsData options,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            CancellationToken cancellationToken = default);

        /// <summary>
        /// Launches the bundled BakeAndRenderStillTiled script: delegates a simulation bake, then
        /// renders the baked frame split into tiles across the crowd.
        /// </summary>
        Task<RunRenderStillTiledResponse> RunBakeAndRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            CancellationToken cancellationToken = default);

        /// <summary>
        /// Launches the bundled BakeAndRenderFrames script: delegates a simulation bake, then renders
        /// the baked frame range distributed.
        /// </summary>
        Task<RunRenderFramesResponse> RunBakeAndRenderFramesAsync(
            Guid sceneBlobId,
            int startFrame,
            int endFrame,
            RenderOptionsData options,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            CancellationToken cancellationToken = default);

        /// <summary>
        /// Launches the bundled BakeAndRenderVideo script: delegates a simulation bake, renders the
        /// baked frame range distributed, then encodes the result to a video.
        /// </summary>
        Task<RunRenderVideoResponse> RunBakeAndRenderVideoAsync(
            Guid sceneBlobId,
            int startFrame,
            int endFrame,
            RenderOptionsData options,
            VideoOptionsData video,
            IReadOnlyList<RenderSceneAttachmentRefData>? attachedFiles = null,
            Guid? selectedClientGroupId = null,
            CancellationToken cancellationToken = default);
    }
}
