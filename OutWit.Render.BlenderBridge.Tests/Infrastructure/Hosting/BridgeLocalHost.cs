using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Channels;
using OutWit.Render.BlenderBridge.Channels.Interfaces;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Models;
using OutWit.Render.BlenderBridge.Services.Auth;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;
using OutWit.Render.BlenderBridge.Services.Cloud;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;
using OutWit.Render.BlenderBridge.Services.Hosting;
using OutWit.Render.BlenderBridge.Services.Hosting.Interfaces;
using OutWit.Render.BlenderBridge.Services.Render;
using OutWit.Render.BlenderBridge.Services.Render.Interfaces;
using OutWit.Render.BlenderBridge.Tests.Infrastructure.Auth;

namespace OutWit.Render.BlenderBridge.Tests.Infrastructure.Hosting
{
    internal sealed class BridgeLocalHost : IAsyncDisposable
    {
        #region Fields

        private readonly IHost m_host;

        #endregion

        #region Constructors

        public BridgeLocalHost(
            string identityUrl,
            string localRestUrl,
            string sessionDir,
            BridgeStartupSecretMode startupSecretMode = BridgeStartupSecretMode.Disabled,
            IBridgeCloudConnectionService? cloudConnectionService = null,
            string serverUrl = "https://cloud.example.com",
            string? downloadCachePath = null)
        {
            var builder = Host.CreateApplicationBuilder();
            builder.Logging.AddSimpleConsole();
            builder.Services.AddSingleton(new BridgeSettings
            {
                ServerUrl = serverUrl,
                IdentityUrl = identityUrl,
                LocalRestUrl = localRestUrl,
                SessionStoragePath = sessionDir,
                DownloadCachePath = downloadCachePath ?? sessionDir,
                StartupSecretMode = startupSecretMode,
                LeaseHeartbeatIntervalSeconds = 5,
                LeaseTimeoutSeconds = 30,
                OrphanGracePeriodSeconds = 600,
                WatchdogIntervalSeconds = 5
            });
            builder.Services.AddSingletonWithInject<IBridgeSystemBrowserLauncher, BridgeHttpGetBrowserLauncher>();
            builder.Services.AddSingletonWithInject<IBridgeAuthorizationCallbackListenerFactory, BridgeAuthorizationCallbackListenerFactory>();
            builder.Services.AddSingletonWithInject<IBridgeLocalSessionSecretService, BridgeLocalSessionSecretService>();
            builder.Services.AddSingletonWithInject<IBridgeLocalConnectionContextService, BridgeLocalConnectionContextService>();
            builder.Services.AddSingletonWithInject<IBridgeLeaseService, BridgeLeaseService>();
            builder.Services.AddSingletonWithInject<IBridgeJobTrackerService, BridgeJobTrackerService>();
            builder.Services.AddSingletonWithInject<IBridgeSessionStore, BridgeSessionStore>();
            builder.Services.AddSingletonWithInject<IBridgeSessionService, BridgeSessionService>();

            if (cloudConnectionService == null)
                builder.Services.AddSingletonWithInject<IBridgeCloudConnectionService, BridgeCloudConnectionService>();
            else
                builder.Services.AddSingleton<IBridgeCloudConnectionService>(cloudConnectionService);

            builder.Services.AddSingletonWithInject<IBridgeExecutionScopeService, BridgeExecutionScopeService>();
            builder.Services.AddSingletonWithInject<IBridgeBlobTransferService, BridgeBlobTransferService>();
            builder.Services.AddSingletonWithInject<IBridgeRenderLaunchService, BridgeRenderLaunchService>();
            builder.Services.AddSingletonWithInject<IBridgeJobQueryService, BridgeJobQueryService>();
            builder.Services.AddSingletonWithInject<IBridgeDownloadService, BridgeDownloadService>();
            builder.Services.AddSingletonWithInject<IBlenderBridgeChannel, BlenderBridgeChannel>();
            builder.Services.AddHostedService<BridgeRestServerService>();
            builder.Services.AddHostedService<BridgeLeaseWatchdogService>();
            m_host = builder.Build();
        }

        #endregion

        #region Functions

        public async Task StartAsync()
        {
            await m_host.StartAsync();
        }

        public string GetLocalConnectionContextPath()
        {
            return m_host.Services.GetRequiredService<IBridgeLocalConnectionContextService>().GetContextFilePath();
        }

        public BridgeLocalConnectionContext GetLocalConnectionContext()
        {
            return m_host.Services.GetRequiredService<IBridgeLocalConnectionContextService>().GetCurrentContext();
        }

        #endregion

        #region IAsyncDisposable

        public async ValueTask DisposeAsync()
        {
            await m_host.StopAsync();
            m_host.Dispose();
        }

        #endregion
    }
}
