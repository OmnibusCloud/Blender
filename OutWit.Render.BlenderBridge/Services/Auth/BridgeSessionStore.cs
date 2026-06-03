using System.Text.Json;
using Microsoft.Extensions.Logging;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Models;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Auth
{
    /// <summary>
    /// File-backed fallback bridge session store.
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

            await using var stream = File.OpenRead(path);
            return await JsonSerializer.DeserializeAsync<BridgeStoredSession>(stream, cancellationToken: cancellationToken);
        }

        public async Task SaveAsync(BridgeStoredSession session, CancellationToken cancellationToken = default)
        {
            var path = GetSessionFilePath();
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);

            await using var stream = File.Create(path);
            await JsonSerializer.SerializeAsync(stream, session, cancellationToken: cancellationToken);
            Logger.LogInformation("Bridge session persisted to local fallback storage.");
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

        private string GetSessionFilePath()
        {
            var configured = Settings.SessionStoragePath;
            if (Path.IsPathRooted(configured))
                return Path.Combine(configured, "bridge-session.json");

            return Path.Combine(AppContext.BaseDirectory, configured, "bridge-session.json");
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
