using System.Net;
using System.Net.Http.Headers;
using OutWit.Render.BlenderBridge.Channels.Interfaces;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Tests.Infrastructure.Hosting;
using static OutWit.Render.BlenderBridge.Tests.Infrastructure.Transport.BridgeRestTestUtils;

namespace OutWit.Render.BlenderBridge.Tests.Integration
{
    /// <summary>
    /// Pure-local bridge REST tests — they exercise the addon↔bridge transport surface
    /// (startup secret, connection-context file lifecycle, lease acquire/ping/release) without
    /// any cloud connection. The cloud-dependent render flows live in the live tier
    /// (<see cref="BridgeRestLiveIntegrationTests"/>) and the in-process Engine.Sdk local tier.
    /// </summary>
    [TestFixture]
    [NonParallelizable]
    public class BridgeRestIntegrationTests
    {
        #region Tests

        [Test]
        public async Task LocalRestBridgeChannelRequiresBearerSecretWhenStartupSecretEnabledTest()
        {
            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17780/bridge/";

            try
            {
                await using var bridgeHost = new BridgeLocalHost("http://127.0.0.1:5701", localRestUrl, tempDir, BridgeStartupSecretMode.GeneratedPerProcess);
                await bridgeHost.StartAsync();

                using var unauthorizedHttp = new HttpClient();
                var unauthorized = await SendRawGetAsync(unauthorizedHttp, localRestUrl, nameof(IBlenderBridgeChannel.GetBridgeStatusAsync));

                var contextPath = bridgeHost.GetLocalConnectionContextPath();
                var connectionContext = await ReadConnectionContextAsync(contextPath);

                using var authorizedHttp = new HttpClient();
                authorizedHttp.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", connectionContext.SessionSecret);
                var authorized = await SendGetAsync<BridgeStatusResponse>(authorizedHttp, localRestUrl, nameof(IBlenderBridgeChannel.GetBridgeStatusAsync));

                Assert.Multiple(() =>
                {
                    Assert.That(File.Exists(contextPath), Is.True);
                    Assert.That(connectionContext.LocalRestUrl, Is.EqualTo(localRestUrl));
                    Assert.That(connectionContext.IsSecretRequired, Is.True);
                    Assert.That(connectionContext.SessionSecret, Is.Not.Null.And.Not.Empty);
                    Assert.That(connectionContext.CreatedUtc, Is.Not.Null.And.Not.Empty);
                    Assert.That((HttpStatusCode)unauthorized.Status, Is.EqualTo(HttpStatusCode.BadRequest));
                    Assert.That(unauthorized.ErrorDetails ?? unauthorized.ErrorMessage ?? string.Empty, Does.Contain("Authorization"));
                    Assert.That(authorized.IsSignedIn, Is.False);
                });
            }
            finally
            {
                DeleteTempDirectory(tempDir);
            }
        }

        [Test]
        public async Task LocalConnectionContextFileIsRemovedWhenBridgeStopsTest()
        {
            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17781/bridge/";

            try
            {
                var bridgeHost = new BridgeLocalHost("http://127.0.0.1:5701", localRestUrl, tempDir, BridgeStartupSecretMode.GeneratedPerProcess);
                await bridgeHost.StartAsync();

                var contextPath = bridgeHost.GetLocalConnectionContextPath();
                Assert.That(File.Exists(contextPath), Is.True);

                await bridgeHost.DisposeAsync();

                Assert.That(File.Exists(contextPath), Is.False);
            }
            finally
            {
                DeleteTempDirectory(tempDir);
            }
        }

        [Test]
        public async Task LeaseAcquirePingAndReleaseThroughLocalRestBridgePostCallsTest()
        {
            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17791/bridge/";

            try
            {
                await using var bridgeHost = new BridgeLocalHost("http://127.0.0.1:5701", localRestUrl, tempDir);
                await bridgeHost.StartAsync();

                using var http = new HttpClient();
                var leaseId = Guid.NewGuid().ToString("N");

                var acquire = await SendPostAsync<AcquireLeaseResponse>(
                    http,
                    localRestUrl,
                    nameof(IBlenderBridgeChannel.AcquireLeaseAsync),
                    12345,
                    leaseId,
                    "0.1.0");
                var ping = await SendPostAsync<bool>(http, localRestUrl, nameof(IBlenderBridgeChannel.PingLeaseAsync), leaseId);
                var release = await SendPostAsync<bool>(http, localRestUrl, nameof(IBlenderBridgeChannel.ReleaseLeaseAsync), leaseId);

                Assert.Multiple(() =>
                {
                    Assert.That(acquire.LeaseAccepted, Is.True);
                    Assert.That(acquire.LeaseId, Is.EqualTo(leaseId));
                    Assert.That(acquire.HeartbeatIntervalSeconds, Is.EqualTo(5));
                    Assert.That(acquire.LeaseTimeoutSeconds, Is.EqualTo(30));
                    Assert.That(ping, Is.True);
                    Assert.That(release, Is.True);
                });
            }
            finally
            {
                DeleteTempDirectory(tempDir);
            }
        }

        #endregion
    }
}
