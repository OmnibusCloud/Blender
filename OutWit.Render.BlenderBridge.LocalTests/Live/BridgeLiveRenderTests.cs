using System.Net.Http;
using OutWit.Cloud.Data.Processing;
using OutWit.Controller.Render.Model;
using OutWit.Render.BlenderBridge.Channels.Interfaces;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Tests.Infrastructure.Hosting;
using static OutWit.Render.BlenderBridge.Tests.Infrastructure.Transport.BridgeRestTestUtils;

namespace OutWit.Render.BlenderBridge.LocalTests.Live
{
    /// <summary>
    /// Tier-A (live) integration: the full bridge stack runs against the REAL deployed
    /// OmnibusCloud server through the public SDK (API-key auth). <c>[Explicit]</c> and env-gated on
    /// <c>OMNIBUSCLOUD_API_KEY</c>; self-skips when capacity is unavailable. Uses the same input
    /// scenes (bundled benchmark, or <c>@Data</c> overrides) and keeps results under
    /// <c>@Output/live/&lt;test&gt;/</c> as the local tier.
    /// </summary>
    [TestFixture]
    [Explicit("Live integration against the deployed OmnibusCloud instance. Set OMNIBUSCLOUD_API_KEY to enable.")]
    [NonParallelizable]
    internal sealed class BridgeLiveRenderTests
    {
        #region Constants

        private static readonly TimeSpan TIMEOUT = TimeSpan.FromMinutes(15);
        private static readonly TimeSpan POLL = TimeSpan.FromSeconds(2);

        private const string STILL_SCENE = "benchmark_scene_still.blend";
        private const string VIDEO_SCENE = "benchmark_scene_video.blend";

        #endregion

        #region Fields

        private LiveCloudConnectionService m_connection = null!;

        #endregion

        #region Setup

        [OneTimeSetUp]
        public async Task SetupAsync()
        {
            if (!LiveIntegrationSettings.IsConfigured)
                Assert.Ignore("Live integration skipped: set OMNIBUSCLOUD_API_KEY (and optionally OMNIBUSCLOUD_SERVER_URL / OMNIBUSCLOUD_IDENTITY_URL).");

            using var cts = new CancellationTokenSource(TimeSpan.FromMinutes(2));
            m_connection = new LiveCloudConnectionService(
                LiveIntegrationSettings.ServerUrl,
                LiveIntegrationSettings.IdentityUrl,
                LiveIntegrationSettings.ApiKey!);

            if (!await m_connection.EnsureConnectedAsync(cts.Token))
                Assert.Fail("Could not connect to the deployed OmnibusCloud API.");
        }

        [OneTimeTearDown]
        public async Task TearDownAsync()
        {
            if (m_connection != null)
                await m_connection.DisconnectAsync();
        }

        #endregion

        #region Tests

        [Test]
        public async Task ValidateBlendAgainstLiveServerReturnsValidationResultTest()
        {
            var scenePath = TestPaths.ResolveScene(STILL_SCENE);
            await RunBridgeAsync(17841, async (http, url, _) =>
            {
                var upload = await UploadAsync(http, url, scenePath);
                var validation = await SendGetAsync<RenderValidateBlendResponse>(http, url, nameof(IBlenderBridgeChannel.RunRenderValidateBlendAsync), upload.BlobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(upload.Uploaded, Is.True);
                    Assert.That(validation.Completed, Is.True, validation.Message);
                    Assert.That(validation.IsValid, Is.True, string.Join("; ", validation.Issues ?? []));
                    Assert.That(validation.Status, Is.EqualTo("Completed"));
                });
            });
        }

        [Test]
        public async Task RenderStillGetJobAndDownloadAgainstLiveServerReturnsLocalPngTest()
        {
            var scenePath = TestPaths.ResolveScene(STILL_SCENE);
            await RunBridgeAsync(17842, async (http, url, outputDir) =>
            {
                var upload = await UploadAsync(http, url, scenePath);
                var launch = await SendPostAsync<RunRenderStillResponse>(
                    http, url, nameof(IBlenderBridgeChannel.RunRenderStillAsync),
                    upload.BlobId, 1, Options());
                var job = await WaitForJobCompletionAsync(http, url, launch.JobId);
                var download = await SendGetAsync<DownloadResultResponse>(http, url, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(job.ScriptName, Is.EqualTo("RenderStillCycles"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(job.ResultBlobId, Is.Not.Null.And.Not.EqualTo(Guid.Empty));
                    Assert.That(download.FileName, Does.EndWith(".png"));
                    Assert.That(download.FileSize, Is.GreaterThan(0));
                    Assert.That(File.Exists(download.LocalPath), Is.True);
                });
                Report(outputDir, download);
            });
        }

        [Test]
        public async Task RenderFramesGetJobAndDownloadAgainstLiveServerReturnsLocalPngsTest()
        {
            var scenePath = TestPaths.ResolveScene(VIDEO_SCENE);
            await RunBridgeAsync(17843, async (http, url, outputDir) =>
            {
                var upload = await UploadAsync(http, url, scenePath);
                var launch = await SendPostAsync<RunRenderFramesResponse>(
                    http, url, nameof(IBlenderBridgeChannel.RunRenderFramesAsync),
                    upload.BlobId, 1, 2, Options());
                var job = await WaitForJobCompletionAsync(http, url, launch.JobId);
                var download = await SendGetAsync<DownloadResultResponse>(http, url, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(job.ScriptName, Is.EqualTo("RenderFramesCycles"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(job.ResultBlobIds, Has.Count.EqualTo(2));
                    Assert.That(download.Items, Has.Count.EqualTo(2));
                    Assert.That(download.Items.All(me => me.FileSize > 0), Is.True);
                });
                Report(outputDir, download);
            });
        }

        [Test]
        public async Task RenderVideoGetJobAndDownloadAgainstLiveServerReturnsLocalMp4Test()
        {
            var scenePath = TestPaths.ResolveScene(VIDEO_SCENE);
            await RunBridgeAsync(17844, async (http, url, outputDir) =>
            {
                var upload = await UploadAsync(http, url, scenePath);
                var launch = await SendPostAsync<RunRenderVideoResponse>(
                    http, url, nameof(IBlenderBridgeChannel.RunRenderVideoAsync),
                    upload.BlobId, 1, 2, Options(), Video());
                var job = await WaitForJobCompletionAsync(http, url, launch.JobId);
                var download = await SendGetAsync<DownloadResultResponse>(http, url, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(job.ScriptName, Is.EqualTo("RenderVideoCycles"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(download.FileName, Does.EndWith(".mp4"));
                    Assert.That(download.FileSize, Is.GreaterThan(0));
                });
                Report(outputDir, download);
            });
        }

        #endregion

        #region Tools

        private async Task RunBridgeAsync(int port, Func<HttpClient, string, string, Task> body, [System.Runtime.CompilerServices.CallerMemberName] string testName = "")
        {
            var localRestUrl = $"http://127.0.0.1:{port}/bridge/";
            var sessionDir = Path.Combine(Path.GetTempPath(), "BridgeLiveRenderTests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(sessionDir);
            var outputDir = TestPaths.OutputDir("live", testName);

            try
            {
                await using var bridgeHost = new BridgeLocalHost(
                    identityUrl: LiveIntegrationSettings.IdentityUrl,
                    localRestUrl: localRestUrl,
                    sessionDir: sessionDir,
                    cloudConnectionService: m_connection,
                    serverUrl: LiveIntegrationSettings.ServerUrl,
                    downloadCachePath: outputDir);
                await bridgeHost.StartAsync();
                using var http = new HttpClient();
                await body(http, localRestUrl, outputDir);
            }
            finally
            {
                if (Directory.Exists(sessionDir))
                {
                    try { Directory.Delete(sessionDir, recursive: true); }
                    catch { /* best-effort */ }
                }
            }
        }

        private static Task<UploadBlendResponse> UploadAsync(HttpClient http, string localRestUrl, string scenePath)
            => SendGetAsync<UploadBlendResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.UploadBlendAsync), scenePath);

        private static void Report(string outputDir, DownloadResultResponse download)
        {
            TestContext.Progress.WriteLine($"[live render output] {download.Items.Count} file(s) in: {outputDir}");
            foreach (var item in download.Items)
                TestContext.Progress.WriteLine($"  - {item.FileName} ({item.FileSize} bytes) -> {item.LocalPath}");
        }

        private static RenderOptionsData Options()
        {
            return new RenderOptionsData
            {
                Format = RenderFormat.PNG,
                Engine = RenderEngine.Cycles,
                Samples = 4,
                ResolutionX = 128,
                ResolutionY = 128
            };
        }

        private static VideoOptionsData Video()
        {
            return new VideoOptionsData { FrameRate = 24, ConstantRateFactor = 23 };
        }

        private static async Task<GetJobResponse> WaitForJobCompletionAsync(HttpClient http, string localRestUrl, Guid jobId)
        {
            var started = DateTime.UtcNow;
            string? last = null;
            while (DateTime.UtcNow - started < TIMEOUT)
            {
                var job = await SendGetAsync<GetJobResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.GetJobAsync), jobId.ToString());
                if (last != job.Status)
                {
                    TestContext.Progress.WriteLine($"Live job {jobId}: {job.Status} ({job.OverallProgress:P0}) {job.ErrorMessage}");
                    last = job.Status;
                }

                if (string.Equals(job.Status, ProcessingJobStatus.Failed.ToString(), StringComparison.OrdinalIgnoreCase))
                {
                    if (!string.IsNullOrWhiteSpace(job.ErrorMessage) && job.ErrorMessage.Contains("No fallback nodes available", StringComparison.OrdinalIgnoreCase))
                        Assert.Ignore($"Live render skipped — deployed capacity unavailable: {job.ErrorMessage}");

                    Assert.Fail($"Live job {jobId} failed: {job.ErrorMessage}");
                }

                if (job.IsCompleted)
                    return job;

                await Task.Delay(POLL);
            }

            Assert.Fail($"Live job {jobId} did not complete within {TIMEOUT}.");
            return null!;
        }

        #endregion
    }
}
