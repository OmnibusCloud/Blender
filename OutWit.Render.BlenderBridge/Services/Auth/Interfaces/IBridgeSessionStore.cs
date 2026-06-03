using OutWit.Render.BlenderBridge.Models;

namespace OutWit.Render.BlenderBridge.Services.Auth.Interfaces
{
    /// <summary>
    /// Persists and loads bridge session state for simple session restore.
    /// </summary>
    public interface IBridgeSessionStore
    {
        /// <summary>
        /// Loads the persisted bridge session if present.
        /// </summary>
        Task<BridgeStoredSession?> LoadAsync(CancellationToken cancellationToken = default);

        /// <summary>
        /// Persists the current bridge session.
        /// </summary>
        Task SaveAsync(BridgeStoredSession session, CancellationToken cancellationToken = default);

        /// <summary>
        /// Clears any persisted bridge session.
        /// </summary>
        Task ClearAsync(CancellationToken cancellationToken = default);
    }
}
