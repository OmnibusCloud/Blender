using OutWit.Cloud.SDK;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;

namespace OutWit.Render.BlenderBridge.Tests.Infrastructure.Cloud
{
    /// <summary>
    /// Tier-A (live) bridge cloud connection: authenticates with a service-to-service API key and
    /// connects to a deployed WitCloud / OmnibusCloud server through the public OutWit.Cloud.SDK,
    /// exactly as a headless third-party initiator would. All token acquisition + WitRPC wiring is
    /// owned by <see cref="WitCloudClient"/>; this adapter only manages the connection lifetime so
    /// it can be injected into <c>BridgeLocalHost</c> in place of the interactive-OIDC production
    /// connection service.
    /// </summary>
    internal sealed class BridgeLiveCloudConnectionService : IBridgeCloudConnectionService
    {
        #region Fields

        private readonly string m_serverUrl;
        private readonly string m_identityUrl;
        private readonly string m_apiKey;
        private WitCloudClient? m_client;

        #endregion

        #region Constructors

        public BridgeLiveCloudConnectionService(string serverUrl, string identityUrl, string apiKey)
        {
            m_serverUrl = serverUrl;
            m_identityUrl = identityUrl;
            m_apiKey = apiKey;
        }

        #endregion

        #region IBridgeCloudConnectionService

        public async Task<bool> EnsureConnectedAsync(CancellationToken cancellationToken = default)
        {
            if (m_client != null)
                return true;

            var client = new WitCloudClient(m_serverUrl, m_identityUrl, m_apiKey);
            try
            {
                await client.ConnectAsync(cancellationToken);
            }
            catch
            {
                await client.DisposeAsync();
                return false;
            }

            m_client = client;
            return true;
        }

        public Task<bool> IsConnectedAsync(CancellationToken cancellationToken = default)
        {
            return Task.FromResult(m_client != null);
        }

        public async Task<IWitCloudClient?> GetClientAsync(CancellationToken cancellationToken = default)
        {
            var connected = await EnsureConnectedAsync(cancellationToken);
            return connected ? m_client : null;
        }

        #endregion

        #region Tools

        public async Task DisconnectAsync()
        {
            if (m_client != null)
                await m_client.DisposeAsync();

            m_client = null;
        }

        #endregion
    }
}
