using System.Diagnostics;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Models;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Auth
{
    /// <summary>
    /// Persists the local bridge connection context file for addon discovery.
    /// </summary>
    [InjectableHost]
    public partial class BridgeLocalConnectionContextService : IBridgeLocalConnectionContextService
    {
        #region Constants

        private const string FILE_PREFIX = "bridge-local-connection.";
        private const string FILE_SUFFIX = ".json";

        #endregion

        #region IBridgeLocalConnectionContextService

        public string GetContextFilePath()
        {
            return Path.Combine(GetContextDirectoryPath(), $"{FILE_PREFIX}{Process.GetCurrentProcess().Id}{FILE_SUFFIX}");
        }

        public BridgeLocalConnectionContext GetCurrentContext()
        {
            return new BridgeLocalConnectionContext
            {
                LocalRestUrl = Settings.LocalRestUrl,
                IsSecretRequired = LocalSessionSecretService.IsSecretRequired,
                SessionSecret = LocalSessionSecretService.GetCurrentSecret(),
                BridgeProcessId = Process.GetCurrentProcess().Id,
                CreatedUtc = DateTime.UtcNow.ToString("O")
            };
        }

        public async Task WriteCurrentContextAsync(CancellationToken cancellationToken = default)
        {
            var path = GetContextFilePath();
            var directory = GetContextDirectoryPath();
            Directory.CreateDirectory(directory);
            DeleteStaleContextFiles(directory, Process.GetCurrentProcess().Id);

            await using var stream = File.Create(path);
            await JsonSerializer.SerializeAsync(stream, GetCurrentContext(), cancellationToken: cancellationToken);
            Logger.LogInformation("Bridge local connection context written to {ContextPath}", path);
        }

        public Task DeleteCurrentContextAsync(CancellationToken cancellationToken = default)
        {
            var path = GetContextFilePath();
            if (File.Exists(path))
                File.Delete(path);

            Logger.LogInformation("Bridge local connection context removed from {ContextPath}", path);
            return Task.CompletedTask;
        }

        #endregion

        #region Tools

        private string GetContextDirectoryPath()
        {
            var configured = Settings.SessionStoragePath;
            if (Path.IsPathRooted(configured))
                return configured;

            return Path.Combine(AppContext.BaseDirectory, configured);
        }

        private void DeleteStaleContextFiles(string directory, int currentProcessId)
        {
            foreach (var path in Directory.EnumerateFiles(directory, $"{FILE_PREFIX}*{FILE_SUFFIX}"))
            {
                var fileName = Path.GetFileName(path);
                var pidText = fileName.Substring(FILE_PREFIX.Length, fileName.Length - FILE_PREFIX.Length - FILE_SUFFIX.Length);
                if (!int.TryParse(pidText, out var pid))
                    continue;

                if (pid == currentProcessId || IsProcessAlive(pid))
                    continue;

                try
                {
                    File.Delete(path);
                    Logger.LogInformation("Removed stale bridge local connection context {ContextPath} for dead process {ProcessId}", path, pid);
                }
                catch (Exception ex)
                {
                    Logger.LogWarning(ex, "Failed to remove stale bridge local connection context {ContextPath}", path);
                }
            }
        }

        private static bool IsProcessAlive(int processId)
        {
            try
            {
                var process = Process.GetProcessById(processId);
                return !process.HasExited;
            }
            catch
            {
                return false;
            }
        }

        #endregion

        #region Properties

        [Inject]
        public BridgeSettings Settings { get; set; } = null!;

        [Inject]
        public IBridgeLocalSessionSecretService LocalSessionSecretService { get; set; } = null!;

        [Inject]
        public ILogger<BridgeLocalConnectionContextService> Logger { get; set; } = null!;

        #endregion
    }
}
