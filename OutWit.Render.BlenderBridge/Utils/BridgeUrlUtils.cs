namespace OutWit.Render.BlenderBridge.Utils
{
    /// <summary>
    /// URL helpers for bridge-side local and cloud connection setup.
    /// </summary>
    public static class BridgeUrlUtils
    {
        #region Functions

        /// <summary>
        /// Converts an HTTP(S) URL to a WebSocket URL.
        /// </summary>
        public static string ToWebSocketUrl(string url)
        {
            if (url.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
                return "wss://" + url[8..];

            if (url.StartsWith("http://", StringComparison.OrdinalIgnoreCase))
                return "ws://" + url[7..];

            return url;
        }

        #endregion
    }
}
