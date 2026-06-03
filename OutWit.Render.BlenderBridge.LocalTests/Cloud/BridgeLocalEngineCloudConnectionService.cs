using OutWit.Cloud.SDK;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;

namespace OutWit.Render.BlenderBridge.LocalTests.Cloud
{
    /// <summary>
    /// Tier-B cloud connection: hands the bridge a <see cref="LocalEngineWitCloudClient"/> instead of
    /// a live WitRPC connection. Injected into <c>BridgeLocalHost</c> in place of the interactive-OIDC
    /// (or Tier-A API-key) connection service, so the entire bridge stack runs against the real
    /// controller in-process.
    /// </summary>
    internal sealed class BridgeLocalEngineCloudConnectionService : IBridgeCloudConnectionService
    {
        #region Fields

        private readonly IWitCloudClient m_client;

        #endregion

        #region Constructors

        public BridgeLocalEngineCloudConnectionService(IWitCloudClient client)
        {
            m_client = client;
        }

        #endregion

        #region IBridgeCloudConnectionService

        public Task<bool> EnsureConnectedAsync(CancellationToken cancellationToken = default) => Task.FromResult(true);

        public Task<bool> IsConnectedAsync(CancellationToken cancellationToken = default) => Task.FromResult(true);

        public Task<IWitCloudClient?> GetClientAsync(CancellationToken cancellationToken = default) => Task.FromResult<IWitCloudClient?>(m_client);

        #endregion
    }
}
