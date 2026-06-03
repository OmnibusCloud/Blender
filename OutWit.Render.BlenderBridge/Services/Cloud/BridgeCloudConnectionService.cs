using Microsoft.Extensions.Logging;
using OutWit.Cloud.SDK;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Cloud
{
    /// <summary>
    /// Bridge-side authenticated cloud connection lifecycle, built on the public
    /// <see cref="WitCloudClient"/>. Authentication uses the SDK token-provider seam fed by the
    /// bridge's interactive sign-in (<see cref="IBridgeSessionService"/>), so the bridge behaves
    /// exactly like any third-party initiator that performed an OIDC login itself.
    /// </summary>
    [InjectableHost]
    public partial class BridgeCloudConnectionService : IBridgeCloudConnectionService
    {
        #region Fields

        private IWitCloudClient? m_client;
        private string? m_connectedAccessToken;
        private bool m_connected;

        #endregion

        #region IBridgeCloudConnectionService

        public async Task<bool> EnsureConnectedAsync(CancellationToken cancellationToken = default)
        {
            var accessToken = await SessionService.GetAccessTokenAsync(cancellationToken);
            if (string.IsNullOrWhiteSpace(accessToken))
            {
                Logger.LogInformation("Bridge cloud connection is not available because no user access token is present.");
                return false;
            }

            if (m_connected && m_client != null && string.Equals(m_connectedAccessToken, accessToken, StringComparison.Ordinal))
                return true;

            await DisconnectCoreAsync();

            // The token-provider is invoked by the SDK on connect/reconnect, so the live session
            // token (incl. silent refresh) is always used without rebuilding the client.
            var client = new WitCloudClient(
                Settings.ServerUrl,
                async ct => await SessionService.GetAccessTokenAsync(ct) ?? string.Empty);

            try
            {
                await client.ConnectAsync(cancellationToken);
            }
            catch (Exception ex)
            {
                Logger.LogWarning(ex, "Bridge failed to connect to cloud endpoint {ServerUrl}.", Settings.ServerUrl);
                await client.DisposeAsync();
                return false;
            }

            m_client = client;
            m_connected = true;
            m_connectedAccessToken = accessToken;
            Logger.LogInformation("Bridge connected to cloud endpoint {ServerUrl}.", Settings.ServerUrl);
            return true;
        }

        public Task<bool> IsConnectedAsync(CancellationToken cancellationToken = default)
        {
            return Task.FromResult(m_connected && m_client != null);
        }

        public async Task<IWitCloudClient?> GetClientAsync(CancellationToken cancellationToken = default)
        {
            var connected = await EnsureConnectedAsync(cancellationToken);
            return connected ? m_client : null;
        }

        #endregion

        #region Tools

        private async Task DisconnectCoreAsync()
        {
            if (m_client != null)
                await m_client.DisposeAsync();

            m_client = null;
            m_connected = false;
            m_connectedAccessToken = null;
        }

        #endregion

        #region Properties

        [Inject]
        public Configuration.BridgeSettings Settings { get; set; } = null!;

        [Inject]
        public IBridgeSessionService SessionService { get; set; } = null!;

        [Inject]
        public ILogger<BridgeCloudConnectionService> Logger { get; set; } = null!;

        #endregion
    }
}
