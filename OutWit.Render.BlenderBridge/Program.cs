using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OutWit.Common.DependencyInjection;
using OutWit.Common.Settings;
using OutWit.Common.Settings.Configuration;
using OutWit.Common.Settings.Json;
using OutWit.Render.BlenderBridge.Channels;
using OutWit.Render.BlenderBridge.Channels.Interfaces;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Services.Auth;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;
using OutWit.Render.BlenderBridge.Services.Cloud;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;
using OutWit.Render.BlenderBridge.Services.Hosting;
using OutWit.Render.BlenderBridge.Services.Render;
using OutWit.Render.BlenderBridge.Services.Render.Interfaces;
using Serilog;

namespace OutWit.Render.BlenderBridge
{
    /// <summary>
    /// Entry point for the Blender bridge scaffold.
    /// </summary>
    public static class BlenderBridgeProgram
    {
        #region Functions

        public static async Task Main(string[] args)
        {
            var builder = Host.CreateApplicationBuilder(args);
            builder.Configuration.AddJsonFile("settings.json", optional: false, reloadOnChange: false);

            var settingsSection = builder.Configuration.GetSection("Bridge");
            var startupSecretModeText = settingsSection["StartupSecretMode"];
            // Secure by default: a missing/unparseable setting enables the per-process local secret
            // rather than leaving the loopback REST surface open. The addon already reads the secret
            // from the connection-context file and sends it as a bearer (bridge_client._apply_secret).
            if (!Enum.TryParse(startupSecretModeText, ignoreCase: true, out BridgeStartupSecretMode startupSecretMode))
                startupSecretMode = BridgeStartupSecretMode.GeneratedPerProcess;

            var settings = new BridgeSettings
            {
                ServerUrl = settingsSection["ServerUrl"] ?? throw new InvalidOperationException("Missing Bridge:ServerUrl setting."),
                IdentityUrl = settingsSection["IdentityUrl"] ?? throw new InvalidOperationException("Missing Bridge:IdentityUrl setting."),
                LocalRestUrl = settingsSection["LocalRestUrl"] ?? throw new InvalidOperationException("Missing Bridge:LocalRestUrl setting."),
                SessionStoragePath = settingsSection["SessionStoragePath"] ?? throw new InvalidOperationException("Missing Bridge:SessionStoragePath setting."),
                DownloadCachePath = settingsSection["DownloadCachePath"] ?? throw new InvalidOperationException("Missing Bridge:DownloadCachePath setting."),
                StartupSecretMode = startupSecretMode,
                LeaseHeartbeatIntervalSeconds = int.TryParse(settingsSection["LeaseHeartbeatIntervalSeconds"], out var leaseHeartbeatIntervalSeconds)
                    ? leaseHeartbeatIntervalSeconds
                    : throw new InvalidOperationException("Missing Bridge:LeaseHeartbeatIntervalSeconds setting."),
                LeaseTimeoutSeconds = int.TryParse(settingsSection["LeaseTimeoutSeconds"], out var leaseTimeoutSeconds)
                    ? leaseTimeoutSeconds
                    : throw new InvalidOperationException("Missing Bridge:LeaseTimeoutSeconds setting."),
                OrphanGracePeriodSeconds = int.TryParse(settingsSection["OrphanGracePeriodSeconds"], out var orphanGracePeriodSeconds)
                    ? orphanGracePeriodSeconds
                    : throw new InvalidOperationException("Missing Bridge:OrphanGracePeriodSeconds setting."),
                WatchdogIntervalSeconds = int.TryParse(settingsSection["WatchdogIntervalSeconds"], out var watchdogIntervalSeconds)
                    ? watchdogIntervalSeconds
                    : throw new InvalidOperationException("Missing Bridge:WatchdogIntervalSeconds setting.")
            };

            ValidateSettings(settings);

            var logPath = ResolveLogPath(settings);
            var logger = new LoggerConfiguration()
                .MinimumLevel.Debug()
                .WriteTo.File(logPath,
                    rollingInterval: RollingInterval.Day,
                    outputTemplate: "[{Timestamp:yyyy-MM-dd HH:mm:ss.fff} {Level:u3}] {SourceContext}{NewLine}{Message:lj}{NewLine}{Exception}")
                .CreateLogger();

            builder.Logging.ClearProviders();
            builder.Logging.AddSimpleConsole(options =>
            {
                options.SingleLine = true;
                options.TimestampFormat = "HH:mm:ss ";
            });
            builder.Services.AddSerilog(logger, dispose: true);

            builder.Services.AddSingleton(settings);

            // Per-OS-user render PREFERENCES (Phase 5): immutable defaults are embedded in the binary
            // (render-settings.json resource); the writable user store is a JSON file next to the
            // encrypted bridge session (%appdata%/OmnibusCloud/Bridge/render-settings.json — survives
            // addon reinstalls). AddSettings merges defaults into the user store and loads it, and
            // registers ISettingsManager + BridgeRenderSettings as singletons. The OIDC refresh token
            // is NOT here — it stays in its own DPAPI-encrypted store (BridgeSessionStore). A corrupt
            // user store self-heals (quarantined to *.corrupt, defaults win) — it cannot kill startup.
            builder.Services.AddSettings(s => s
                .UseJsonResource(typeof(BlenderBridgeProgram).Assembly, "render-settings.json")
                .UseJsonFile(
                    Utils.BridgeUserStorageUtils.ResolveUserDataFilePath(settings, "render-settings.json"),
                    SettingsScope.User)
                .RegisterContainer<BridgeRenderSettings>());

            builder.Services.AddSingletonWithInject<IBridgeSystemBrowserLauncher, BridgeSystemBrowserLauncher>();
            builder.Services.AddSingletonWithInject<IBridgeAuthorizationCallbackListenerFactory, BridgeAuthorizationCallbackListenerFactory>();
            builder.Services.AddSingletonWithInject<IBridgeLocalSessionSecretService, BridgeLocalSessionSecretService>();
            builder.Services.AddSingletonWithInject<IBridgeLocalConnectionContextService, BridgeLocalConnectionContextService>();
            builder.Services.AddSingletonWithInject<Services.Hosting.Interfaces.IBridgeLeaseService, Services.Hosting.BridgeLeaseService>();
            builder.Services.AddSingletonWithInject<Services.Hosting.Interfaces.IBridgeJobTrackerService, Services.Hosting.BridgeJobTrackerService>();
            builder.Services.AddSingletonWithInject<IBridgeSessionStore, BridgeSessionStore>();
            builder.Services.AddSingletonWithInject<IBridgeSessionService, BridgeSessionService>();
            builder.Services.AddSingletonWithInject<IBridgeCloudConnectionService, BridgeCloudConnectionService>();
            builder.Services.AddSingletonWithInject<IBridgeExecutionScopeService, BridgeExecutionScopeService>();
            builder.Services.AddSingletonWithInject<IBridgeBlobTransferService, BridgeBlobTransferService>();
            builder.Services.AddSingletonWithInject<IBridgeRenderLaunchService, BridgeRenderLaunchService>();
            builder.Services.AddSingletonWithInject<IBridgeRenderPreferenceService, BridgeRenderPreferenceService>();
            builder.Services.AddSingletonWithInject<IBridgeJobQueryService, BridgeJobQueryService>();
            builder.Services.AddSingletonWithInject<IBridgeDownloadService, BridgeDownloadService>();
            builder.Services.AddSingletonWithInject<IBlenderBridgeChannel, BlenderBridgeChannel>();
            builder.Services.AddHostedService<BridgeRestServerService>();
            builder.Services.AddHostedService<Services.Hosting.BridgeLeaseWatchdogService>();

            using var host = builder.Build();
            var startupLogger = host.Services.GetRequiredService<ILoggerFactory>().CreateLogger(typeof(BlenderBridgeProgram));
            startupLogger.LogInformation("Starting Blender bridge on {LocalRestUrl}", settings.LocalRestUrl);
            startupLogger.LogInformation("Bridge log path: {LogPath}", logPath);

            var sessionService = host.Services.GetRequiredService<IBridgeSessionService>();
            await sessionService.TryRestoreSessionAsync();
            await host.RunAsync();
        }

        private static void ValidateSettings(BridgeSettings settings)
        {
            if (!Uri.TryCreate(settings.ServerUrl, UriKind.Absolute, out _))
                throw new InvalidOperationException($"Bridge:ServerUrl is not a valid absolute URL: '{settings.ServerUrl}'.");

            if (!Uri.TryCreate(settings.IdentityUrl, UriKind.Absolute, out _))
                throw new InvalidOperationException($"Bridge:IdentityUrl is not a valid absolute URL: '{settings.IdentityUrl}'.");

            if (!Uri.TryCreate(settings.LocalRestUrl, UriKind.Absolute, out var localRestUri))
                throw new InvalidOperationException($"Bridge:LocalRestUrl is not a valid absolute URL: '{settings.LocalRestUrl}'.");

            if (!localRestUri.IsLoopback)
                throw new InvalidOperationException($"Bridge:LocalRestUrl must bind to loopback only: '{settings.LocalRestUrl}'.");

            if (string.IsNullOrWhiteSpace(settings.SessionStoragePath))
                throw new InvalidOperationException("Bridge:SessionStoragePath is required.");

            if (string.IsNullOrWhiteSpace(settings.DownloadCachePath))
                throw new InvalidOperationException("Bridge:DownloadCachePath is required.");

            if (settings.LeaseHeartbeatIntervalSeconds <= 0)
                throw new InvalidOperationException("Bridge:LeaseHeartbeatIntervalSeconds must be greater than zero.");

            if (settings.LeaseTimeoutSeconds <= 0)
                throw new InvalidOperationException("Bridge:LeaseTimeoutSeconds must be greater than zero.");

            if (settings.OrphanGracePeriodSeconds < 0)
                throw new InvalidOperationException("Bridge:OrphanGracePeriodSeconds must be zero or greater.");

            if (settings.WatchdogIntervalSeconds <= 0)
                throw new InvalidOperationException("Bridge:WatchdogIntervalSeconds must be greater than zero.");
        }

        private static string ResolveLogPath(BridgeSettings settings)
        {
            // Same per-user log home as the worker client (%appdata%/OmnibusCloud/Logs) so all
            // OmnibusCloud components are discoverable in one place.
            var logDirectory = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                "OmnibusCloud",
                "Logs");
            Directory.CreateDirectory(logDirectory);
            return Path.Combine(logDirectory, "blender-bridge-.log");
        }

        #endregion
    }
}
