using OutWit.Cloud.SDK;

namespace OutWit.Render.BlenderBridge.Services.Cloud.Interfaces
{
    /// <summary>
    /// Owns the bridge-side authenticated cloud connection lifecycle and hands out the connected
    /// <see cref="IWitCloudClient"/>. The public OutWit.Cloud.SDK is the only way this bridge talks
    /// to WitCloud / OmnibusCloud — it behaves exactly like any third-party initiator.
    /// </summary>
    /// <remarks>
    /// The connection is exposed as the SDK interface <see cref="IWitCloudClient"/> (not the concrete
    /// <see cref="WitCloudClient"/>) so the production connection (live OIDC / API-key WitRPC) and
    /// the in-process Engine.Sdk test connection are interchangeable behind one seam.
    /// </remarks>
    public interface IBridgeCloudConnectionService
    {
        /// <summary>
        /// Ensures the bridge has an authenticated cloud connection.
        /// </summary>
        Task<bool> EnsureConnectedAsync(CancellationToken cancellationToken = default);

        /// <summary>
        /// Returns whether the bridge currently has a connected client.
        /// </summary>
        Task<bool> IsConnectedAsync(CancellationToken cancellationToken = default);

        /// <summary>
        /// Returns the connected SDK client, or null when no authenticated session is available.
        /// </summary>
        Task<IWitCloudClient?> GetClientAsync(CancellationToken cancellationToken = default);
    }
}
