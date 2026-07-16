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
        public async Task RenderSettingsGetAndSetRoundTripThroughLocalRestBridgeTest()
        {
            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17792/bridge/";

            try
            {
                await using var bridgeHost = new BridgeLocalHost("http://127.0.0.1:5701", localRestUrl, tempDir);
                await bridgeHost.StartAsync();

                using var http = new HttpClient();

                var defaults = await SendGetAsync<RenderSettingsResponse>(
                    http, localRestUrl, nameof(IBlenderBridgeChannel.GetRenderSettingsAsync));

                var updated = new RenderSettingsResponse
                {
                    RememberRenderSettings = true,
                    SplitFrame = true,
                    TilesX = 3,
                    TilesY = 5,
                    TileOverlap = 16,
                    AnimResult = "Video",
                    LastGroupId = Guid.NewGuid().ToString(),
                    LastGroupName = "My Farm"
                };
                var saved = await SendPostAsync<bool>(
                    http, localRestUrl, nameof(IBlenderBridgeChannel.SetRenderSettingsAsync), updated);
                var restored = await SendGetAsync<RenderSettingsResponse>(
                    http, localRestUrl, nameof(IBlenderBridgeChannel.GetRenderSettingsAsync));

                Assert.Multiple(() =>
                {
                    // The first get returns the embedded-resource defaults.
                    Assert.That(defaults.RememberRenderSettings, Is.True);
                    Assert.That(defaults.SplitFrame, Is.False);
                    Assert.That(defaults.TilesX, Is.EqualTo(2));
                    Assert.That(defaults.TilesY, Is.EqualTo(2));
                    Assert.That(defaults.TileOverlap, Is.EqualTo(8));
                    Assert.That(defaults.AnimResult, Is.EqualTo("Sequence"));

                    Assert.That(saved, Is.True);
                    Assert.That(restored.Is(updated), Is.True, "the set snapshot must read back unchanged");
                    Assert.That(File.Exists(Path.Combine(tempDir, "render-settings.json")), Is.True,
                        "the per-user store must materialize in the rooted storage dir");
                });
            }
            finally
            {
                DeleteTempDirectory(tempDir);
            }
        }

        [Test]
        public async Task DownloadStatusEndpointsRespondThroughLocalRestBridgeTest()
        {
            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17793/bridge/";

            try
            {
                await using var bridgeHost = new BridgeLocalHost("http://127.0.0.1:5701", localRestUrl, tempDir);
                await bridgeHost.StartAsync();

                using var http = new HttpClient();
                var jobId = Guid.NewGuid();

                var unknown = await SendPostAsync<DownloadStatusResponse>(
                    http, localRestUrl, nameof(IBlenderBridgeChannel.GetDownloadResultStatusAsync), jobId);
                var cancelled = await SendPostAsync<bool>(
                    http, localRestUrl, nameof(IBlenderBridgeChannel.CancelDownloadResultAsync), jobId);

                // Start with no cloud connection: the endpoint answers immediately and the background
                // transfer fails on its own — the failure surfaces through the polled status, never
                // as a hung or failed REST call.
                var started = await SendPostAsync<DownloadStatusResponse>(
                    http, localRestUrl, nameof(IBlenderBridgeChannel.StartDownloadResultAsync), jobId);

                DownloadStatusResponse terminal;
                var deadline = DateTime.UtcNow.AddSeconds(10);
                do
                {
                    terminal = await SendPostAsync<DownloadStatusResponse>(
                        http, localRestUrl, nameof(IBlenderBridgeChannel.GetDownloadResultStatusAsync), jobId);
                    if (terminal.Status != DownloadStatusResponse.STATUS_IN_PROGRESS)
                        break;
                    await Task.Delay(50);
                } while (DateTime.UtcNow < deadline);

                Assert.Multiple(() =>
                {
                    Assert.That(unknown.Status, Is.EqualTo(DownloadStatusResponse.STATUS_NOT_FOUND));
                    Assert.That(unknown.JobId, Is.EqualTo(jobId));
                    Assert.That(cancelled, Is.False);
                    Assert.That(started.Status, Is.Not.EqualTo(DownloadStatusResponse.STATUS_NOT_FOUND));
                    Assert.That(terminal.Status, Is.EqualTo(DownloadStatusResponse.STATUS_FAILED));
                    Assert.That(terminal.Error, Is.Not.Null.And.Not.Empty);
                });
            }
            finally
            {
                DeleteTempDirectory(tempDir);
            }
        }

        [Test]
        public async Task UploadStatusEndpointsRespondThroughLocalRestBridgeTest()
        {
            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17794/bridge/";

            try
            {
                await using var bridgeHost = new BridgeLocalHost("http://127.0.0.1:5701", localRestUrl, tempDir);
                await bridgeHost.StartAsync();

                using var http = new HttpClient();

                var unknown = await SendPostAsync<UploadStatusResponse>(
                    http, localRestUrl, nameof(IBlenderBridgeChannel.GetUploadStatusAsync), Guid.NewGuid());
                var cancelled = await SendPostAsync<bool>(
                    http, localRestUrl, nameof(IBlenderBridgeChannel.CancelUploadAsync), Guid.NewGuid());

                // Start with no cloud connection: the endpoint answers immediately and the background
                // transfer fails on its own — the failure surfaces through the polled status, never
                // as a hung or failed REST call.
                var filePath = Path.Combine(tempDir, "scene.blend");
                await File.WriteAllBytesAsync(filePath, new byte[1024]);
                var started = await SendPostAsync<UploadStatusResponse>(
                    http, localRestUrl, nameof(IBlenderBridgeChannel.StartUploadBlendAsync), filePath);

                UploadStatusResponse terminal;
                var deadline = DateTime.UtcNow.AddSeconds(10);
                do
                {
                    terminal = await SendPostAsync<UploadStatusResponse>(
                        http, localRestUrl, nameof(IBlenderBridgeChannel.GetUploadStatusAsync), started.TransferId);
                    if (terminal.Status != UploadStatusResponse.STATUS_IN_PROGRESS)
                        break;
                    await Task.Delay(50);
                } while (DateTime.UtcNow < deadline);

                Assert.Multiple(() =>
                {
                    Assert.That(unknown.Status, Is.EqualTo(UploadStatusResponse.STATUS_NOT_FOUND));
                    Assert.That(cancelled, Is.False);
                    Assert.That(started.TransferId, Is.Not.EqualTo(Guid.Empty));
                    Assert.That(started.FileName, Is.EqualTo("scene.blend"));
                    Assert.That(terminal.Status, Is.EqualTo(UploadStatusResponse.STATUS_FAILED));
                    Assert.That(terminal.Error, Is.Not.Null.And.Not.Empty);
                });
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
