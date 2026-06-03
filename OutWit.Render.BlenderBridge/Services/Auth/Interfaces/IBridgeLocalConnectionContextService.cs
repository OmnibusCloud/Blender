using OutWit.Render.BlenderBridge.Models;

namespace OutWit.Render.BlenderBridge.Services.Auth.Interfaces
{
    /// <summary>
    /// Persists the local bridge connection context used by the addon to discover the loopback REST endpoint and bearer secret.
    /// </summary>
    public interface IBridgeLocalConnectionContextService
    {
        /// <summary>
        /// Returns the current local bridge connection context file path.
        /// </summary>
        string GetContextFilePath();

        /// <summary>
        /// Builds the current local bridge connection context.
        /// </summary>
        BridgeLocalConnectionContext GetCurrentContext();

        /// <summary>
        /// Writes the current local bridge connection context to disk.
        /// </summary>
        Task WriteCurrentContextAsync(CancellationToken cancellationToken = default);

        /// <summary>
        /// Deletes any persisted local bridge connection context.
        /// </summary>
        Task DeleteCurrentContextAsync(CancellationToken cancellationToken = default);
    }
}
