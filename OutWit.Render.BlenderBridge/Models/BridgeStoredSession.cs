namespace OutWit.Render.BlenderBridge.Models
{
    /// <summary>
    /// Persisted bridge session state used for simple session restore.
    /// </summary>
    public class BridgeStoredSession
    {
        #region Properties

        public string RefreshToken { get; set; } = string.Empty;

        public string TokenEndpoint { get; set; } = string.Empty;

        public string DisplayName { get; set; } = string.Empty;

        public string UserId { get; set; } = string.Empty;

        public string LastLoginUtc { get; set; } = string.Empty;

        #endregion
    }
}
