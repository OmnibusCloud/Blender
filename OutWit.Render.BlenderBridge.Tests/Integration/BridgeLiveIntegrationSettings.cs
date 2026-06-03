namespace OutWit.Render.BlenderBridge.Tests.Integration
{
    /// <summary>
    /// Tier-A (live) integration settings, sourced from environment variables so no credential is
    /// ever committed. The live fixtures are <c>[Explicit]</c> and additionally self-skip when
    /// <see cref="IsConfigured"/> is false, so the suite stays green on machines without an API key.
    /// </summary>
    /// <remarks>
    /// Required: <c>OMNIBUSCLOUD_API_KEY</c> — a service-to-service API key minted in the WitIdentity
    /// admin UI for the deployed OmnibusCloud instance.
    /// Optional overrides: <c>OMNIBUSCLOUD_SERVER_URL</c>, <c>OMNIBUSCLOUD_IDENTITY_URL</c>.
    /// </remarks>
    internal static class BridgeLiveIntegrationSettings
    {
        #region Constants

        private const string DEFAULT_SERVER_URL = "http://engine.omnibuscloud.com";

        private const string DEFAULT_IDENTITY_URL = "https://id.waveslogic.com";

        #endregion

        #region Properties

        public static string ServerUrl =>
            Environment.GetEnvironmentVariable("OMNIBUSCLOUD_SERVER_URL") is { Length: > 0 } url
                ? url
                : DEFAULT_SERVER_URL;

        public static string IdentityUrl =>
            Environment.GetEnvironmentVariable("OMNIBUSCLOUD_IDENTITY_URL") is { Length: > 0 } url
                ? url
                : DEFAULT_IDENTITY_URL;

        public static string? ApiKey =>
            Environment.GetEnvironmentVariable("OMNIBUSCLOUD_API_KEY") is { Length: > 0 } key
                ? key
                : null;

        public static bool IsConfigured => !string.IsNullOrWhiteSpace(ApiKey);

        #endregion
    }
}
