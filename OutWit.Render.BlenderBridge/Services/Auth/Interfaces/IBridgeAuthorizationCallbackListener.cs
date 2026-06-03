namespace OutWit.Render.BlenderBridge.Services.Auth.Interfaces
{
    /// <summary>
    /// Listens for the local OAuth authorization callback.
    /// </summary>
    public interface IBridgeAuthorizationCallbackListener : IDisposable
    {
        /// <summary>
        /// Starts the listener and returns the bound redirect URI.
        /// </summary>
        string? TryStart();

        /// <summary>
        /// Waits for the authorization callback and returns the authorization code.
        /// </summary>
        /// <param name="expectedState">The state value to validate the callback against (CSRF).</param>
        /// <param name="completionUrl">
        /// Optional URL of the shared WitIdentity completion page (e.g. "{IdentityUrl}/auth/complete").
        /// When supplied, the browser is redirected there after the callback (success) or with
        /// "status=error" appended (failure), so every native client shows the same branded page.
        /// When null/empty, a built-in inline HTML response is served as a fallback.
        /// </param>
        /// <param name="cancellationToken">Cancellation token.</param>
        Task<string?> WaitForCallbackAsync(string expectedState, string? completionUrl, CancellationToken cancellationToken);
    }
}
