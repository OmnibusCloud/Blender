namespace OutWit.Render.BlenderBridge.LocalTests.Live
{
    /// <summary>
    /// Tier-A (live) settings, sourced from environment variables so no credential is committed.
    /// The live fixture is <c>[Explicit]</c> and additionally self-skips when
    /// <see cref="IsConfigured"/> is false.
    /// </summary>
    /// <remarks>
    /// Required: <c>OMNIBUSCLOUD_API_KEY</c> — a service-to-service API key minted in the WitIdentity
    /// admin UI for the deployed OmnibusCloud instance.
    /// Optional overrides: <c>OMNIBUSCLOUD_SERVER_URL</c>, <c>OMNIBUSCLOUD_IDENTITY_URL</c>.
    /// </remarks>
    internal static class LiveIntegrationSettings
    {
        #region Constants

        private const string DEFAULT_SERVER_URL = "https://engine.omnibuscloud.com";

        private const string DEFAULT_IDENTITY_URL = "https://auth.omnibuscloud.com";

        #endregion

        #region Properties

        public static string ServerUrl =>
            Environment.GetEnvironmentVariable("OMNIBUSCLOUD_SERVER_URL") is { Length: > 0 } url ? url : DEFAULT_SERVER_URL;

        public static string IdentityUrl =>
            Environment.GetEnvironmentVariable("OMNIBUSCLOUD_IDENTITY_URL") is { Length: > 0 } url ? url : DEFAULT_IDENTITY_URL;

        public static string? ApiKey =>
            Environment.GetEnvironmentVariable("OMNIBUSCLOUD_API_KEY") is { Length: > 0 } key ? key : null;

        public static bool IsConfigured => !string.IsNullOrWhiteSpace(ApiKey);

        #endregion
    }
}
