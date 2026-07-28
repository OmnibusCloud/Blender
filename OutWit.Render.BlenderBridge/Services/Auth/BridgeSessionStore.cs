using OutWit.Cloud.Auth.Sessions;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;
using OutWit.Render.BlenderBridge.Utils;

namespace OutWit.Render.BlenderBridge.Services.Auth
{
    /// <summary>
    /// Injectable wrapper around the shared OutWit.Cloud.Auth <see cref="SessionStore"/>. The store
    /// keeps the persisted session (the OIDC refresh token) in the same per-OS-user file the bridge
    /// always used (bridge-session.json under the per-user data directory, overridable by a rooted
    /// <see cref="BridgeSettings.SessionStoragePath"/>), encrypted at rest by the package (DPAPI on
    /// Windows, Keychain / Secret Service where available). A corrupt, foreign or legacy-format file
    /// fails closed (load returns null → clean re-login) rather than crashing the bridge.
    /// </summary>
    [InjectableHost]
    public partial class BridgeSessionStore : IBridgeSessionStore
    {
        #region Constants

        private const string SESSION_FILE_NAME = "bridge-session.json";

        #endregion

        #region Fields

        private SessionStore? m_store;

        #endregion

        #region IBridgeSessionStore

        public SessionStore Store =>
            m_store ??= new SessionStore(
                BridgeUserStorageUtils.ResolveUserDataFilePath(Settings, SESSION_FILE_NAME),
                Logger);

        #endregion

        #region Properties

        [Inject]
        public BridgeSettings Settings { get; set; } = null!;

        [Inject]
        public Serilog.ILogger Logger { get; set; } = null!;

        #endregion
    }
}
