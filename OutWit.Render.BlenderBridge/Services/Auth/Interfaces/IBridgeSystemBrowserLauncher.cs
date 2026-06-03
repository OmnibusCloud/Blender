namespace OutWit.Render.BlenderBridge.Services.Auth.Interfaces
{
    /// <summary>
    /// Opens the system browser for bridge-side interactive authentication.
    /// </summary>
    public interface IBridgeSystemBrowserLauncher
    {
        /// <summary>
        /// Opens the specified URL in the current platform browser shell.
        /// </summary>
        Task OpenAsync(string url);
    }
}
