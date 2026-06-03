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
            CancellationToken cancellationToken = default);
    }
}
