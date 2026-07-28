using System.IdentityModel.Tokens.Jwt;
using Microsoft.Extensions.Logging;
using OutWit.Cloud.Auth;
using OutWit.Cloud.Auth.Interfaces;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Models;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Auth
{
    /// <summary>
    /// Thin adapter over the shared OutWit.Cloud.Auth <see cref="OutWit.Cloud.Auth.TokenService"/>.
    /// The package owns the OIDC machinery (discovery, PKCE, loopback callback, refresh-token
    /// rotation and permanent-vs-transient refresh semantics, encrypted session persistence);
    /// this class preserves the bridge's WitRPC-facing session surface for the Blender addon
    /// and keeps the display-name / user-id JWT claim parsing adapter-local.
    /// </summary>
    public class BridgeSessionService : IBridgeSessionService
    {
        #region Constants

        private const string CLIENT_ID = "cloud-client";
        private const SessionPolicy SESSION_POLICY = SessionPolicy.RememberUntilLogout;
        private const string NO_SESSION_ERROR = "No active bridge user session.";

        #endregion

        #region Fields

        private TokenService? m_tokenService;
        private bool m_isSignedIn;
        private string? m_displayName;
        private string? m_userId;
        private string? m_lastError;

        #endregion

        #region Constructors

        public BridgeSessionService(IServiceProvider services)
        {
            Services = services;
            m_lastError = NO_SESSION_ERROR;
        }

        #endregion

        #region Initialization

        private TokenService CreateTokenService()
        {
            // The bridge keeps its historical OIDC client id ("cloud-client") — the package
            // default ("omnibuscloud-client") belongs to the worker client.
            var tokenService = new TokenService(AuthLogger, BrowserLauncher, CallbackListenerFactory, CLIENT_ID);
            tokenService.RefreshTokenRotated += OnRefreshTokenRotated;
            tokenService.ReauthenticationRequired += OnReauthenticationRequired;
            return tokenService;
        }

        #endregion

        #region IBridgeSessionService

        public async Task<bool> TryRestoreSessionAsync(CancellationToken cancellationToken = default)
        {
            var restored = await TokenService.TryRestoreSessionAsync(SESSION_POLICY, SessionStore.Store);
            if (!restored)
                return false;

            await UpdateIdentityAsync();
            m_isSignedIn = true;
            ClearLastError();
            Logger.LogInformation("Bridge session restored successfully.");
            return true;
        }

        public async Task<BeginSignInResponse> BeginSignInAsync(CancellationToken cancellationToken = default)
        {
            ClearLastError();

            try
            {
                var succeeded = await TokenService.LoginWithBrowserAsync(Settings.IdentityUrl);
                if (!succeeded)
                {
                    SetLastError(string.IsNullOrWhiteSpace(TokenService.LastInteractiveFailureText)
                        ? "Interactive sign-in failed."
                        : TokenService.LastInteractiveFailureText);

                    return new BeginSignInResponse
                    {
                        Started = false,
                        RequiresBrowser = true,
                        Message = m_lastError
                    };
                }

                TokenService.SaveSession(SESSION_POLICY, SessionStore.Store);
                await UpdateIdentityAsync();
                m_isSignedIn = true;

                Logger.LogInformation("Bridge sign-in completed. SignedIn={IsSignedIn}, UserId={UserId}, DisplayName={DisplayName}",
                    m_isSignedIn,
                    m_userId,
                    m_displayName);

                return new BeginSignInResponse
                {
                    Started = true,
                    RequiresBrowser = true,
                    Message = "Bridge sign-in completed successfully."
                };
            }
            catch (Exception ex)
            {
                SetLastError(ex.Message);
                Logger.LogError(ex, "Bridge interactive sign-in failed.");

                return new BeginSignInResponse
                {
                    Started = false,
                    RequiresBrowser = true,
                    Message = m_lastError
                };
            }
        }

        public Task<bool> SignOutAsync(CancellationToken cancellationToken = default)
        {
            // ClearSession removes the persisted session AND clears the in-memory token cache.
            TokenService.ClearSession(SessionStore.Store);
            ClearIdentity();
            SetLastError(NO_SESSION_ERROR);
            Logger.LogInformation("Bridge session cleared.");
            return Task.FromResult(true);
        }

        public Task<BridgeSessionStateSnapshot> GetSessionStateAsync(CancellationToken cancellationToken = default)
        {
            var snapshot = new BridgeSessionStateSnapshot
            {
                IsSignedIn = m_isSignedIn,
                DisplayName = m_displayName,
                UserId = m_userId,
                CanLaunch = m_isSignedIn,
                NeedsInteractiveLogin = !m_isSignedIn,
                LastError = m_lastError
            };

            Logger.LogInformation("Bridge session snapshot requested. SignedIn={IsSignedIn}, CanLaunch={CanLaunch}, UserId={UserId}, LastError={LastError}",
                snapshot.IsSignedIn,
                snapshot.CanLaunch,
                snapshot.UserId,
                snapshot.LastError);

            return Task.FromResult(snapshot);
        }

        public async Task<string?> GetAccessTokenAsync(CancellationToken cancellationToken = default)
        {
            // GetTokenAsync refreshes on demand; a rotated refresh token is persisted through
            // the RefreshTokenRotated subscription, a permanently dead one surfaces through
            // ReauthenticationRequired.
            var accessToken = await TokenService.GetTokenAsync();
            return string.IsNullOrWhiteSpace(accessToken) ? null : accessToken;
        }

        #endregion

        #region Tools

        private async Task UpdateIdentityAsync()
        {
            var accessToken = await TokenService.GetTokenAsync();
            if (string.IsNullOrWhiteSpace(accessToken))
                return;

            var token = new JwtSecurityTokenHandler().ReadJwtToken(accessToken);
            m_userId = token.Claims.FirstOrDefault(me => me.Type == "sub")?.Value;
            m_displayName = token.Claims.FirstOrDefault(me => me.Type == "name")?.Value
                ?? token.Claims.FirstOrDefault(me => me.Type == "preferred_username")?.Value
                ?? token.Claims.FirstOrDefault(me => me.Type == "email")?.Value
                ?? m_userId;
        }

        private void ClearIdentity()
        {
            m_isSignedIn = false;
            m_displayName = null;
            m_userId = null;
        }

        private void SetLastError(string? text)
        {
            m_lastError = text;
        }

        private void ClearLastError()
        {
            m_lastError = null;
        }

        #endregion

        #region Event Handlers

        private void OnRefreshTokenRotated()
        {
            // Without persisting the rotated token, the next bridge start would attempt the
            // now-revoked previous one and fall back to interactive login.
            TokenService.SaveSession(SESSION_POLICY, SessionStore.Store);
        }

        private void OnReauthenticationRequired()
        {
            // The refresh token is permanently dead (expired / revoked). Drop the persisted
            // session too, so the next start goes straight to interactive login instead of
            // retrying a dead credential.
            SessionStore.Store.Clear();
            ClearIdentity();
            SetLastError("Bridge session expired or was revoked; interactive sign-in is required.");
            Logger.LogWarning("Bridge session requires interactive re-authentication.");
        }

        #endregion

        #region Properties

        protected IServiceProvider Services { get; }

        private TokenService TokenService => m_tokenService ??= CreateTokenService();

        [Inject]
        public BridgeSettings Settings { get; set; } = null!;

        [Inject]
        public ISystemBrowserLauncher BrowserLauncher { get; set; } = null!;

        [Inject]
        public IAuthorizationCallbackListenerFactory CallbackListenerFactory { get; set; } = null!;

        [Inject]
        public IBridgeSessionStore SessionStore { get; set; } = null!;

        [Inject]
        public Serilog.ILogger AuthLogger { get; set; } = null!;

        [Inject]
        public ILogger<BridgeSessionService> Logger { get; set; } = null!;

        #endregion
    }
}
