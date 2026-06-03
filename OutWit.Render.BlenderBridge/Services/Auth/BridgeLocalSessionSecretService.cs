using Microsoft.Extensions.Logging;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;
using OutWit.Render.BlenderBridge.Utils;

namespace OutWit.Render.BlenderBridge.Services.Auth
{
    /// <summary>
    /// Generates and exposes the local bridge REST bearer secret.
    /// </summary>
    [InjectableHost]
    public partial class BridgeLocalSessionSecretService : IBridgeLocalSessionSecretService
    {
        #region Fields

        private string? m_secret;

        #endregion

        #region IBridgeLocalSessionSecretService

        public bool IsSecretRequired => Settings.StartupSecretMode != BridgeStartupSecretMode.Disabled;

        public string? GetCurrentSecret()
        {
            if (!IsSecretRequired)
                return null;

            m_secret ??= CreateSecret();
            return m_secret;
        }

        #endregion

        #region Tools

        private string CreateSecret()
        {
            var secret = BridgeSessionSecretUtils.GenerateSecret();
            Logger.LogInformation("Bridge local REST session secret generated for the current process.");
            return secret;
        }

        #endregion

        #region Properties

        [Inject]
        public BridgeSettings Settings { get; set; } = null!;

        [Inject]
        public ILogger<BridgeLocalSessionSecretService> Logger { get; set; } = null!;

        #endregion
    }
}
