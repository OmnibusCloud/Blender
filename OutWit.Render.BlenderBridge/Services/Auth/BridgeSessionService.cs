using System.IdentityModel.Tokens.Jwt;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using Microsoft.IdentityModel.Protocols;
using Microsoft.IdentityModel.Protocols.OpenIdConnect;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Models;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;
using OutWit.Render.BlenderBridge.Utils;

namespace OutWit.Render.BlenderBridge.Services.Auth
{
    /// <summary>
    /// First-slice in-memory bridge session service.
    /// </summary>
    public class BridgeSessionService : IBridgeSessionService
    {
        #region Constants

        private const string CLIENT_ID = "cloud-client";
        private const string SCOPE = "openid profile roles offline_access";
        private const int TOKEN_EXPIRY_BUFFER_SECONDS = 30;
        private const int AUTH_TIMEOUT_SECONDS = 300;

        #endregion

        #region Fields

        private string? m_accessToken;
        private DateTime m_accessTokenExpiry;
        private string? m_refreshToken;
        private string? m_tokenEndpoint;
        private bool m_isSignedIn;
        private string? m_displayName;
        private string? m_userId;
        private string? m_lastError;

        #endregion

        #region Constructors

        public BridgeSessionService(IServiceProvider services)
        {
            Services = services;
            m_accessTokenExpiry = DateTime.MinValue;
            m_lastError = "No active bridge user session.";
        }

        #endregion

        #region IBridgeSessionService

        public async Task<bool> TryRestoreSessionAsync(CancellationToken cancellationToken = default)
        {
            var storedSession = await SessionStore.LoadAsync(cancellationToken);
            if (storedSession == null || string.IsNullOrWhiteSpace(storedSession.RefreshToken) || string.IsNullOrWhiteSpace(storedSession.TokenEndpoint))
                return false;

            m_refreshToken = storedSession.RefreshToken;
            m_tokenEndpoint = storedSession.TokenEndpoint;
            m_displayName = string.IsNullOrWhiteSpace(storedSession.DisplayName) ? null : storedSession.DisplayName;
            m_userId = string.IsNullOrWhiteSpace(storedSession.UserId) ? null : storedSession.UserId;

            var restored = await RefreshTokenAsync(cancellationToken);
            if (!restored)
            {
                await SessionStore.ClearAsync(cancellationToken);
                ClearRuntimeSession();
                return false;
            }

            await SaveCurrentSessionAsync(cancellationToken);
            Logger.LogInformation("Bridge session restored successfully.");
            return true;
        }

        public async Task<BeginSignInResponse> BeginSignInAsync(CancellationToken cancellationToken = default)
        {
            ClearLastError();

            try
            {
                var endpoints = await DiscoverEndpointsAsync(Settings.IdentityUrl, cancellationToken);
                if (endpoints == null)
                {
                    return new BeginSignInResponse
                    {
                        Started = false,
                        RequiresBrowser = true,
                        Message = m_lastError
                    };
                }

                m_tokenEndpoint = endpoints.TokenEndpoint;

                var codeVerifier = BridgePkceUtils.GenerateCodeVerifier();
                var codeChallenge = BridgePkceUtils.ComputeCodeChallenge(codeVerifier);
                var state = Guid.NewGuid().ToString("N");

                using var listener = CallbackListenerFactory.Create();
                var redirectUri = listener.TryStart();
                if (redirectUri == null)
                {
                    SetLastError("Interactive authentication failed because the local loopback callback listener could not start.");
                    return new BeginSignInResponse
                    {
                        Started = false,
                        RequiresBrowser = true,
                        Message = m_lastError
                    };
                }

                var authorizeUrl = BuildAuthorizeUrl(endpoints.AuthorizationEndpoint, redirectUri, codeChallenge, state);
                await BrowserLauncher.OpenAsync(authorizeUrl);

                using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                cts.CancelAfter(TimeSpan.FromSeconds(AUTH_TIMEOUT_SECONDS));

                // After capturing the code, the listener redirects the browser to WitIdentity's
                // shared completion page so the user sees the same branded "signed in" screen as
                // every other native client (the worker, the 3ds Max bridge).
                var completionUrl = $"{Settings.IdentityUrl.TrimEnd('/')}/auth/complete";
                var code = await listener.WaitForCallbackAsync(state, completionUrl, cts.Token);
                if (string.IsNullOrWhiteSpace(code))
                {
                    SetLastError("Interactive authentication timed out or was cancelled while waiting for the browser callback.");
                    return new BeginSignInResponse
                    {
                        Started = false,
                        RequiresBrowser = true,
                        Message = m_lastError
                    };
                }

                var exchanged = await ExchangeCodeForTokensAsync(code, redirectUri, codeVerifier, cancellationToken);
                if (!exchanged)
                {
                    return new BeginSignInResponse
                    {
                        Started = false,
                        RequiresBrowser = true,
                        Message = m_lastError
                    };
                }

                await SaveCurrentSessionAsync(cancellationToken);
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

        public async Task<bool> SignOutAsync(CancellationToken cancellationToken = default)
        {
            await SessionStore.ClearAsync(cancellationToken);
            ClearRuntimeSession();
            SetLastError("No active bridge user session.");
            Logger.LogInformation("Bridge session cleared.");
            return true;
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
            if (!string.IsNullOrWhiteSpace(m_accessToken) && DateTime.UtcNow < m_accessTokenExpiry)
                return m_accessToken;

            if (!string.IsNullOrWhiteSpace(m_refreshToken) && !string.IsNullOrWhiteSpace(m_tokenEndpoint))
            {
                var refreshed = await RefreshTokenAsync(cancellationToken);
                if (refreshed)
                {
                    await SaveCurrentSessionAsync(cancellationToken);
                    return m_accessToken;
                }
            }

            return null;
        }

        #endregion

        #region Tools

        private async Task<BridgeOidcEndpoints?> DiscoverEndpointsAsync(string identityUrl, CancellationToken cancellationToken)
        {
            try
            {
                var discoveryUrl = $"{identityUrl.TrimEnd('/')}/.well-known/openid-configuration";
                var requireHttps = identityUrl.StartsWith("https://", StringComparison.OrdinalIgnoreCase);

                var configManager = new ConfigurationManager<OpenIdConnectConfiguration>(
                    discoveryUrl,
                    new OpenIdConnectConfigurationRetriever(),
                    new HttpDocumentRetriever
                    {
                        RequireHttps = requireHttps
                    });

                var config = await configManager.GetConfigurationAsync(cancellationToken);
                if (string.IsNullOrWhiteSpace(config.TokenEndpoint) || string.IsNullOrWhiteSpace(config.AuthorizationEndpoint))
                {
                    SetLastError("Identity discovery succeeded but the required authorization/token endpoints were missing.");
                    return null;
                }

                return new BridgeOidcEndpoints
                {
                    TokenEndpoint = config.TokenEndpoint,
                    AuthorizationEndpoint = config.AuthorizationEndpoint
                };
            }
            catch (Exception ex)
            {
                SetLastError($"Failed to discover identity configuration from {identityUrl.TrimEnd('/')}/.well-known/openid-configuration.");
                Logger.LogError(ex, "Bridge OIDC discovery failed.");
                return null;
            }
        }

        private static string BuildAuthorizeUrl(string authorizationEndpoint, string redirectUri, string codeChallenge, string state)
        {
            var parameters = new Dictionary<string, string>
            {
                ["client_id"] = CLIENT_ID,
                ["response_type"] = "code",
                ["redirect_uri"] = redirectUri,
                ["scope"] = SCOPE,
                ["code_challenge"] = codeChallenge,
                ["code_challenge_method"] = "S256",
                ["state"] = state
            };

            var query = string.Join("&", parameters.Select(me => $"{Uri.EscapeDataString(me.Key)}={Uri.EscapeDataString(me.Value)}"));
            return $"{authorizationEndpoint}?{query}";
        }

        private async Task<bool> ExchangeCodeForTokensAsync(string code, string redirectUri, string codeVerifier, CancellationToken cancellationToken)
        {
            try
            {
                using var httpClient = new HttpClient();
                var content = new FormUrlEncodedContent(new Dictionary<string, string>
                {
                    ["grant_type"] = "authorization_code",
                    ["client_id"] = CLIENT_ID,
                    ["code"] = code,
                    ["redirect_uri"] = redirectUri,
                    ["code_verifier"] = codeVerifier
                });

                var response = await httpClient.PostAsync(m_tokenEndpoint, content, cancellationToken);
                if (!response.IsSuccessStatusCode)
                {
                    SetLastError($"Interactive authentication token exchange failed with status {(int)response.StatusCode}.");
                    return false;
                }

                var json = await response.Content.ReadAsStringAsync(cancellationToken);
                var tokenResponse = JsonSerializer.Deserialize<JsonElement>(json);

                m_accessToken = tokenResponse.GetProperty("access_token").GetString();
                m_refreshToken = tokenResponse.TryGetProperty("refresh_token", out var refreshProp)
                    ? refreshProp.GetString()
                    : null;

                var expiresIn = tokenResponse.GetProperty("expires_in").GetInt32();
                m_accessTokenExpiry = DateTime.UtcNow.AddSeconds(expiresIn - TOKEN_EXPIRY_BUFFER_SECONDS);
                UpdateIdentityFromAccessToken();
                m_isSignedIn = !string.IsNullOrWhiteSpace(m_accessToken);
                ClearLastError();
                return m_isSignedIn;
            }
            catch (Exception ex)
            {
                SetLastError("Interactive authentication token exchange failed unexpectedly.");
                Logger.LogError(ex, "Bridge token exchange failed.");
                return false;
            }
        }

        private async Task<bool> RefreshTokenAsync(CancellationToken cancellationToken)
        {
            try
            {
                using var httpClient = new HttpClient();
                var content = new FormUrlEncodedContent(new Dictionary<string, string>
                {
                    ["grant_type"] = "refresh_token",
                    ["client_id"] = CLIENT_ID,
                    ["refresh_token"] = m_refreshToken!
                });

                var response = await httpClient.PostAsync(m_tokenEndpoint, content, cancellationToken);
                if (!response.IsSuccessStatusCode)
                {
                    SetLastError($"Bridge token refresh failed with status {(int)response.StatusCode}.");
                    return false;
                }

                var json = await response.Content.ReadAsStringAsync(cancellationToken);
                var tokenResponse = JsonSerializer.Deserialize<JsonElement>(json);
                m_accessToken = tokenResponse.GetProperty("access_token").GetString();

                if (tokenResponse.TryGetProperty("refresh_token", out var refreshProp))
                    m_refreshToken = refreshProp.GetString();

                var expiresIn = tokenResponse.GetProperty("expires_in").GetInt32();
                m_accessTokenExpiry = DateTime.UtcNow.AddSeconds(expiresIn - TOKEN_EXPIRY_BUFFER_SECONDS);
                UpdateIdentityFromAccessToken();
                m_isSignedIn = !string.IsNullOrWhiteSpace(m_accessToken);
                ClearLastError();
                return m_isSignedIn;
            }
            catch (Exception ex)
            {
                SetLastError("Bridge token refresh failed unexpectedly.");
                Logger.LogError(ex, "Bridge token refresh failed.");
                return false;
            }
        }

        private async Task SaveCurrentSessionAsync(CancellationToken cancellationToken)
        {
            if (string.IsNullOrWhiteSpace(m_refreshToken) || string.IsNullOrWhiteSpace(m_tokenEndpoint))
                return;

            await SessionStore.SaveAsync(new BridgeStoredSession
            {
                RefreshToken = m_refreshToken,
                TokenEndpoint = m_tokenEndpoint,
                DisplayName = m_displayName ?? string.Empty,
                UserId = m_userId ?? string.Empty,
                LastLoginUtc = DateTime.UtcNow.ToString("O")
            }, cancellationToken);
        }

        private void UpdateIdentityFromAccessToken()
        {
            if (string.IsNullOrWhiteSpace(m_accessToken))
                return;

            var token = new JwtSecurityTokenHandler().ReadJwtToken(m_accessToken);
            m_userId = token.Claims.FirstOrDefault(me => me.Type == "sub")?.Value;
            m_displayName = token.Claims.FirstOrDefault(me => me.Type == "name")?.Value
                ?? token.Claims.FirstOrDefault(me => me.Type == "preferred_username")?.Value
                ?? token.Claims.FirstOrDefault(me => me.Type == "email")?.Value
                ?? m_userId;
        }

        private void ClearRuntimeSession()
        {
            m_accessToken = null;
            m_refreshToken = null;
            m_tokenEndpoint = null;
            m_accessTokenExpiry = DateTime.MinValue;
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

        #region Properties

        protected IServiceProvider Services { get; }

        [Inject]
        public BridgeSettings Settings { get; set; } = null!;

        [Inject]
        public IBridgeSystemBrowserLauncher BrowserLauncher { get; set; } = null!;

        [Inject]
        public IBridgeAuthorizationCallbackListenerFactory CallbackListenerFactory { get; set; } = null!;

        [Inject]
        public IBridgeSessionStore SessionStore { get; set; } = null!;

        [Inject]
        public ILogger<BridgeSessionService> Logger { get; set; } = null!;

        #endregion
    }
}
