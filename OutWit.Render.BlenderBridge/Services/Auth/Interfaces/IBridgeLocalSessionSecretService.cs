namespace OutWit.Render.BlenderBridge.Services.Auth.Interfaces
{
    /// <summary>
    /// Owns the local bridge-to-addon session secret used to protect the loopback REST transport.
    /// </summary>
    public interface IBridgeLocalSessionSecretService
    {
        /// <summary>
        /// Returns whether the local REST transport requires a bearer secret.
        /// </summary>
        bool IsSecretRequired { get; }

        /// <summary>
        /// Returns the current local session secret when enabled.
        /// </summary>
        string? GetCurrentSecret();
    }
}
