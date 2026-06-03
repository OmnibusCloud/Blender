using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OutWit.Common.DependencyInjection;
using OutWit.Communication.Server.Authorization;
using OutWit.Communication.Server.Rest;
using OutWit.Render.BlenderBridge.Channels.Interfaces;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;
using OutWit.Render.BlenderBridge.Transport.Rest;

namespace OutWit.Render.BlenderBridge.Services.Hosting
{
    /// <summary>
    /// Hosts the local addon-facing WitRPC server over the REST transport.
    /// </summary>
    [InjectableHost]
    public partial class BridgeRestServerService : IHostedService, IDisposable
    {
        #region Fields

        private WitServerRest? m_server;

        #endregion

        #region IHostedService

        public async Task StartAsync(CancellationToken cancellationToken)
        {
            if (m_server != null)
                return;

            var localSessionSecret = LocalSessionSecretService.GetCurrentSecret();

            m_server = WitServerRestBuilder.Build(options =>
            {
                options.WithUrl(Settings.LocalRestUrl);
                options.WithRequestProcessor(new BridgeRestRequestProcessor<IBlenderBridgeChannel>(BridgeChannel));

                if (string.IsNullOrWhiteSpace(localSessionSecret))
                    options.WithoutAuthorization();
                else
                    options.WithAccessTokenValidator(new AccessTokenValidatorStatic(localSessionSecret));

                options.WithLogger(Logger);
                options.WithTimeout(TimeSpan.FromSeconds(30));
            });

            m_server.StartWaitingForConnection();
            await LocalConnectionContextService.WriteCurrentContextAsync(cancellationToken);
            Logger.LogInformation("Bridge local WitRPC REST server started on {LocalRestUrl}. Local secret required: {SecretRequired}",
                Settings.LocalRestUrl,
                !string.IsNullOrWhiteSpace(localSessionSecret));
        }

        public async Task StopAsync(CancellationToken cancellationToken)
        {
            await LocalConnectionContextService.DeleteCurrentContextAsync(cancellationToken);
            Dispose();
        }

        #endregion

        #region IDisposable

        public void Dispose()
        {
            m_server?.StopWaitingForConnection();
            m_server = null;
        }

        #endregion

        #region Properties

        [Inject]
        public BridgeSettings Settings { get; set; } = null!;

        [Inject]
        public IBlenderBridgeChannel BridgeChannel { get; set; } = null!;

        [Inject]
        public IBridgeLocalSessionSecretService LocalSessionSecretService { get; set; } = null!;

        [Inject]
        public IBridgeLocalConnectionContextService LocalConnectionContextService { get; set; } = null!;

        [Inject]
        public ILogger<BridgeRestServerService> Logger { get; set; } = null!;

        #endregion
    }
}
