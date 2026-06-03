using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Models;

namespace OutWit.Render.BlenderBridge.Services.Auth.Interfaces
{
    /// <summary>
    /// Owns user session state and the future browser-based sign-in flow for the bridge.
    /// </summary>
    public interface IBridgeSessionService
    {
        /// <summary>
        /// Attempts to restore a previously persisted user session.
        /// </summary>
        Task<bool> TryRestoreSessionAsync(CancellationToken cancellationToken = default);

        /// <summary>
        /// Begins interactive user sign-in.
        /// </summary>
        Task<BeginSignInResponse> BeginSignInAsync(CancellationToken cancellationToken = default);

        /// <summary>
        /// Signs the current user out of the bridge session.
        /// </summary>
        Task<bool> SignOutAsync(CancellationToken cancellationToken = default);

        /// <summary>
        /// Returns the current bridge session summary.
        /// </summary>
        Task<BridgeSessionStateSnapshot> GetSessionStateAsync(CancellationToken cancellationToken = default);

        /// <summary>
        /// Returns the current access token when available.
        /// </summary>
        Task<string?> GetAccessTokenAsync(CancellationToken cancellationToken = default);
    }
}
