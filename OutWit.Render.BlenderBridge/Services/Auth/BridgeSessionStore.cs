using System.Runtime.Versioning;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Models;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;
using OutWit.Render.BlenderBridge.Utils;

namespace OutWit.Render.BlenderBridge.Services.Auth
{
    /// <summary>
    /// File-backed fallback bridge session store. The persisted session holds the OIDC refresh token,
    /// so on Windows it is encrypted at rest with DPAPI (CurrentUser scope — only the same OS user can
    /// read it back). On macOS/Linux the payload is written unprotected for now (a real Keychain /
    /// Secret Service backend is the remaining work — see docs/refresh-token-storage.md); an envelope
    /// flag records which, so a DPAPI file fails closed (returns null → re-login) on any other platform
    /// rather than being mis-read.
    /// </summary>
    [InjectableHost]
    public partial class BridgeSessionStore : IBridgeSessionStore
    {
        #region IBridgeSessionStore

        public async Task<BridgeStoredSession?> LoadAsync(CancellationToken cancellationToken = default)
        {
            var path = GetSessionFilePath();
            if (!File.Exists(path))
                return null;

            try
            {
                var envelopeBytes = await File.ReadAllBytesAsync(path, cancellationToken);
                var envelope = JsonSerializer.Deserialize<SessionEnvelope>(envelopeBytes);
                if (envelope?.Payload == null)
                    return null;

                var payload = Convert.FromBase64String(envelope.Payload);

                if (envelope.Protected)
                {
                    if (!OperatingSystem.IsWindows())
                    {
                        Logger.LogWarning("Bridge session is DPAPI-protected but cannot be decrypted on this platform; requiring re-login.");
                        return null;
                    }

                    payload = Unprotect(payload);
                }

                return JsonSerializer.Deserialize<BridgeStoredSession>(payload);
            }
            catch (Exception ex)
            {
                // Corrupt / foreign / undecryptable session → treat as no session (clean re-login)
                // rather than crashing the bridge.
                Logger.LogWarning(ex, "Failed to load persisted bridge session; requiring re-login.");
                return null;
            }
        }

        public async Task SaveAsync(BridgeStoredSession session, CancellationToken cancellationToken = default)
        {
            var path = GetSessionFilePath();
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);

            var json = JsonSerializer.SerializeToUtf8Bytes(session);

            var isProtected = false;
            if (OperatingSystem.IsWindows())
            {
                json = Protect(json);
                isProtected = true;
            }

            var envelope = new SessionEnvelope
            {
                Protected = isProtected,
                Payload = Convert.ToBase64String(json)
            };

            await File.WriteAllBytesAsync(path, JsonSerializer.SerializeToUtf8Bytes(envelope), cancellationToken);
            Logger.LogInformation(
                "Bridge session persisted to local fallback storage (encrypted at rest: {Encrypted}).",
                isProtected);
        }

        public Task ClearAsync(CancellationToken cancellationToken = default)
        {
            var path = GetSessionFilePath();
            if (File.Exists(path))
                File.Delete(path);

            Logger.LogInformation("Bridge session storage cleared.");
            return Task.CompletedTask;
        }

        #endregion

        #region Tools

        [SupportedOSPlatform("windows")]
        private static byte[] Protect(byte[] data)
            => ProtectedData.Protect(data, optionalEntropy: null, DataProtectionScope.CurrentUser);

        [SupportedOSPlatform("windows")]
        private static byte[] Unprotect(byte[] data)
            => ProtectedData.Unprotect(data, optionalEntropy: null, DataProtectionScope.CurrentUser);

        private string GetSessionFilePath()
        {
            // Per-OS-user so the refresh token survives addon reinstalls (see BridgeUserStorageUtils).
            // NOTE: the per-session connection-context file is a SEPARATE concern
            // (BridgeLocalConnectionContextService) and intentionally stays exe-relative,
            // where the addon polls for it.
            return BridgeUserStorageUtils.ResolveUserDataFilePath(Settings, "bridge-session.json");
        }

        #endregion

        #region Models

        private sealed class SessionEnvelope
        {
            public bool Protected { get; set; }

            public string? Payload { get; set; }
        }

        #endregion

        #region Properties

        [Inject]
        public BridgeSettings Settings { get; set; } = null!;

        [Inject]
        public ILogger<BridgeSessionStore> Logger { get; set; } = null!;

        #endregion
    }
}
