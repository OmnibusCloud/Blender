using System.Net;
using Microsoft.Extensions.Logging;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;

namespace OutWit.Render.BlenderBridge.Tests.Infrastructure.Auth
{
    internal class BridgeHttpGetBrowserLauncher : IBridgeSystemBrowserLauncher
    {
        #region Constructors

        public BridgeHttpGetBrowserLauncher(IServiceProvider services)
        {
            Services = services;
        }

        #endregion

        #region IBridgeSystemBrowserLauncher

        public async Task OpenAsync(string url)
        {
            using var httpClient = new HttpClient(new HttpClientHandler
            {
                AllowAutoRedirect = false,
                AutomaticDecompression = DecompressionMethods.All
            });

            using var authorizeResponse = await httpClient.GetAsync(url);
            if (authorizeResponse.Headers.Location != null)
            {
                var callbackUrl = NormalizeLoopbackCallbackUrl(authorizeResponse.Headers.Location.ToString());

                _ = Task.Run(async () =>
                {
                    await Task.Delay(50);

                    using var callbackClient = new HttpClient(new HttpClientHandler
                    {
                        AllowAutoRedirect = false,
                        AutomaticDecompression = DecompressionMethods.All
                    });

                    using var callbackResponse = await callbackClient.GetAsync(callbackUrl);
                    Logger.LogInformation("Bridge test browser callback completed with {StatusCode}", callbackResponse.StatusCode);
                });
            }
        }

        #endregion

        #region Functions

        internal static string NormalizeLoopbackCallbackUrl(string url)
        {
            if (!Uri.TryCreate(url, UriKind.Absolute, out var uri))
                return url;

            var isLoopback = uri.HostNameType switch
            {
                UriHostNameType.IPv4 => IPAddress.TryParse(uri.Host, out var address) && IPAddress.IsLoopback(address),
                UriHostNameType.IPv6 => IPAddress.TryParse(uri.Host, out var address) && IPAddress.IsLoopback(address),
                UriHostNameType.Dns => string.Equals(uri.Host, "localhost", StringComparison.OrdinalIgnoreCase),
                _ => false
            };

            if (!isLoopback)
                return url;

            if (string.Equals(uri.AbsolutePath, "/callback", StringComparison.OrdinalIgnoreCase))
            {
                var builder = new UriBuilder(uri)
                {
                    Path = "/callback/"
                };
                return builder.Uri.ToString();
            }

            return url;
        }

        #endregion

        #region Properties

        protected IServiceProvider Services { get; }

        [Inject]
        public ILogger<BridgeHttpGetBrowserLauncher> Logger { get; set; } = null!;

        #endregion
    }
}
