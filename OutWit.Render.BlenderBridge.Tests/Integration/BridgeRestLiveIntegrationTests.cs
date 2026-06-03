using System.Net.Http;
using OutWit.Cloud.Data.Processing;
using OutWit.Controller.Render.Model;
using OutWit.Render.BlenderBridge.Channels.Interfaces;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Tests.Infrastructure.Cloud;
using OutWit.Render.BlenderBridge.Tests.Infrastructure.Hosting;
using static OutWit.Render.BlenderBridge.Tests.Infrastructure.Transport.BridgeRestTestUtils;

namespace OutWit.Render.BlenderBridge.Tests.Integration
{
    [TestFixture]
    [Explicit("Live external bridge integration test against the deployed OmnibusCloud instance through the local bridge REST transport.")]
    [NonParallelizable]
    public sealed class BridgeRestLiveIntegrationTests
    {
        #region Constants

        private static readonly TimeSpan TIMEOUT = TimeSpan.FromMinutes(10);

        #endregion

        #region Fields

        private BridgeLiveCloudConnectionService m_cloudConnectionService = null!;

        #endregion

        #region Setup

        [OneTimeSetUp]
        public async Task SetupAsync()
        {
            if (!BridgeLiveIntegrationSettings.IsConfigured)
                Assert.Ignore("Live bridge integration skipped: set OMNIBUSCLOUD_API_KEY (and optionally OMNIBUSCLOUD_SERVER_URL / OMNIBUSCLOUD_IDENTITY_URL) to enable.");

            using var cts = new CancellationTokenSource(TIMEOUT);
            m_cloudConnectionService = new BridgeLiveCloudConnectionService(
                BridgeLiveIntegrationSettings.ServerUrl,
                BridgeLiveIntegrationSettings.IdentityUrl,
                BridgeLiveIntegrationSettings.ApiKey!);

            var connected = await m_cloudConnectionService.EnsureConnectedAsync(cts.Token);
            if (!connected)
                Assert.Fail("Live bridge integration failed because the bridge could not connect to the deployed cloud API.");
        }

        [OneTimeTearDown]
        public async Task TearDownAsync()
        {
            if (m_cloudConnectionService != null)
                await m_cloudConnectionService.DisconnectAsync();
        }

        #endregion

        #region Tests

        [Test]
        public async Task UploadBlendAndRunRenderValidateBlendThroughLocalRestBridgeAgainstLiveServerReturnsValidationResultTest()
        {
            var solutionRoot = FindSolutionRoot();
            if (solutionRoot == null)
                Assert.Ignore("Solution root not found.");

            var scenePath = Path.Combine(solutionRoot, "@Data", "cube_diorama", "cube_diorama.blend");
            if (!File.Exists(scenePath))
                Assert.Ignore($"Cube Diorama scene not found at {scenePath}");

            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17801/bridge/";

            try
            {
                await using var bridgeHost = new BridgeLocalHost(
                    BridgeLiveIntegrationSettings.IdentityUrl,
                    localRestUrl,
                    tempDir,
                    cloudConnectionService: m_cloudConnectionService,
                    serverUrl: BridgeLiveIntegrationSettings.ServerUrl);
                await bridgeHost.StartAsync();

                using var http = new HttpClient();
                var upload = await SendGetAsync<UploadBlendResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.UploadBlendAsync), scenePath);
                var validation = await SendGetAsync<RenderValidateBlendResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.RunRenderValidateBlendAsync), upload.BlobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(upload.Uploaded, Is.True);
                    Assert.That(validation.JobId, Is.Not.EqualTo(Guid.Empty));
                    Assert.That(validation.Completed, Is.True);
                    Assert.That(validation.IsValid, Is.True);
                    Assert.That(validation.Issues, Is.Empty);
                    Assert.That(validation.Status, Is.EqualTo("Completed"));
                });
            }
            finally
            {
                DeleteTempDirectory(tempDir);
            }
        }

        [Test]
        public async Task RunRenderPreflightThroughLocalRestBridgeAgainstLiveServerReturnsAggregatedDiagnosticsTest()
        {
            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17802/bridge/";

            try
            {
                await using var bridgeHost = new BridgeLocalHost(
                    BridgeLiveIntegrationSettings.IdentityUrl,
                    localRestUrl,
                    tempDir,
                    cloudConnectionService: m_cloudConnectionService,
                    serverUrl: BridgeLiveIntegrationSettings.ServerUrl);
                await bridgeHost.StartAsync();

                using var http = new HttpClient();
                var preflight = await SendPostAsync<RenderPreflightResponse>(
                    http,
                    localRestUrl,
                    nameof(IBlenderBridgeChannel.RunRenderPreflightAsync),
                    1,
                    1,
                    3,
                    2,
                    2,
                    CreateCubeDioramaOptions(),
                    CreateDefaultAddonTileOptions(),
                    CreateDefaultVideoOptions());

                Assert.Multiple(() =>
                {
                    Assert.That(preflight.Completed, Is.True);
                    Assert.That(preflight.Status, Is.EqualTo("Completed"));
                    Assert.That(preflight.Result, Is.Not.Null);
                    Assert.That(preflight.Result!.CanRenderAll, Is.True);
                    Assert.That(preflight.Result.RuntimeDiagnostics, Is.Not.Null);
                    Assert.That(preflight.Result.Still, Is.Not.Null);
                    Assert.That(preflight.Result.Frames, Is.Not.Null);
                    Assert.That(preflight.Result.StillTiled, Is.Not.Null);
                    Assert.That(preflight.Result.Video, Is.Not.Null);
                });
            }
            finally
            {
                DeleteTempDirectory(tempDir);
            }
        }

        [Test]
        public async Task RunRenderStillGetJobAndDownloadResultThroughLocalRestBridgeAgainstLiveServerReturnsLocalFileTest()
        {
            var solutionRoot = FindSolutionRoot();
            if (solutionRoot == null)
                Assert.Ignore("Solution root not found.");

            var scenePath = Path.Combine(solutionRoot, "@Data", "cube_diorama", "cube_diorama.blend");
            if (!File.Exists(scenePath))
                Assert.Ignore($"Cube Diorama scene not found at {scenePath}");

            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17803/bridge/";

            try
            {
                await using var bridgeHost = new BridgeLocalHost(
                    BridgeLiveIntegrationSettings.IdentityUrl,
                    localRestUrl,
                    tempDir,
                    cloudConnectionService: m_cloudConnectionService,
                    serverUrl: BridgeLiveIntegrationSettings.ServerUrl);
                await bridgeHost.StartAsync();

                using var http = new HttpClient();
                var upload = await SendGetAsync<UploadBlendResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.UploadBlendAsync), scenePath);
                var launch = await SendPostAsync<RunRenderStillResponse>(
                    http,
                    localRestUrl,
                    nameof(IBlenderBridgeChannel.RunRenderStillAsync),
                    upload.BlobId,
                    1,
                    CreateStillOptions());
                var job = await WaitForJobCompletionAsync(http, localRestUrl, launch.JobId, TIMEOUT, TimeSpan.FromSeconds(2));
                var download = await SendGetAsync<DownloadResultResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(upload.Uploaded, Is.True);
                    Assert.That(launch.JobId, Is.Not.EqualTo(Guid.Empty));
                    Assert.That(job.ScriptName, Is.EqualTo("RenderStillCycles"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(job.ResultBlobId, Is.Not.Null.And.Not.EqualTo(Guid.Empty));
                    Assert.That(download.Downloaded, Is.True);
                    Assert.That(download.Items, Has.Count.EqualTo(1));
                    Assert.That(download.FileName, Does.EndWith(".png"));
                    Assert.That(download.FileSize, Is.GreaterThan(0));
                    Assert.That(File.Exists(download.LocalPath), Is.True);
                });
            }
            finally
            {
                DeleteTempDirectory(tempDir);
            }
        }

        [Test]
        public async Task RunRenderStillTiledGetJobAndDownloadResultThroughLocalRestBridgeAgainstLiveServerReturnsLocalFileTest()
        {
            var solutionRoot = FindSolutionRoot();
            if (solutionRoot == null)
                Assert.Ignore("Solution root not found.");

            var scenePath = Path.Combine(solutionRoot, "@Data", "cube_diorama", "cube_diorama.blend");
            if (!File.Exists(scenePath))
                Assert.Ignore($"Cube Diorama scene not found at {scenePath}");

            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17804/bridge/";

            try
            {
                await using var bridgeHost = new BridgeLocalHost(
                    BridgeLiveIntegrationSettings.IdentityUrl,
                    localRestUrl,
                    tempDir,
                    cloudConnectionService: m_cloudConnectionService,
                    serverUrl: BridgeLiveIntegrationSettings.ServerUrl);
                await bridgeHost.StartAsync();

                using var http = new HttpClient();
                var upload = await SendGetAsync<UploadBlendResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.UploadBlendAsync), scenePath);
                var launch = await SendPostAsync<RunRenderStillTiledResponse>(
                    http,
                    localRestUrl,
                    nameof(IBlenderBridgeChannel.RunRenderStillTiledAsync),
                    upload.BlobId,
                    1,
                    2,
                    2,
                    CreateCubeDioramaOptions(),
                    CreateDefaultAddonTileOptions());
                var job = await WaitForJobCompletionAsync(http, localRestUrl, launch.JobId, TIMEOUT, TimeSpan.FromSeconds(2));
                var download = await SendGetAsync<DownloadResultResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(upload.Uploaded, Is.True);
                    Assert.That(launch.JobId, Is.Not.EqualTo(Guid.Empty));
                    Assert.That(job.ScriptName, Is.EqualTo("RenderStillTiledCycles"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(job.ResultBlobId, Is.Not.Null.And.Not.EqualTo(Guid.Empty));
                    Assert.That(download.Downloaded, Is.True);
                    Assert.That(download.Items, Has.Count.EqualTo(1));
                    Assert.That(download.FileName, Does.EndWith(".png"));
                    Assert.That(download.FileSize, Is.GreaterThan(0));
                    Assert.That(File.Exists(download.LocalPath), Is.True);
                });
            }
            finally
            {
                DeleteTempDirectory(tempDir);
            }
        }

        [Test]
        public async Task RunRenderFramesGetJobAndDownloadResultThroughLocalRestBridgeAgainstLiveServerReturnsLocalFilesTest()
        {
            var solutionRoot = FindSolutionRoot();
            if (solutionRoot == null)
                Assert.Ignore("Solution root not found.");

            var scenePath = Path.Combine(solutionRoot, "@Data", "greasepencil-bike.blend");
            if (!File.Exists(scenePath))
                Assert.Ignore($"Bike scene not found at {scenePath}");

            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17805/bridge/";

            try
            {
                await using var bridgeHost = new BridgeLocalHost(
                    BridgeLiveIntegrationSettings.IdentityUrl,
                    localRestUrl,
                    tempDir,
                    cloudConnectionService: m_cloudConnectionService,
                    serverUrl: BridgeLiveIntegrationSettings.ServerUrl);
                await bridgeHost.StartAsync();

                using var http = new HttpClient();
                var upload = await SendGetAsync<UploadBlendResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.UploadBlendAsync), scenePath);
                var launch = await SendPostAsync<RunRenderFramesResponse>(
                    http,
                    localRestUrl,
                    nameof(IBlenderBridgeChannel.RunRenderFramesAsync),
                    upload.BlobId,
                    4,
                    6,
                    CreateBikeFrameOptions());
                var job = await WaitForJobCompletionAsync(http, localRestUrl, launch.JobId, TimeSpan.FromMinutes(20), TimeSpan.FromSeconds(2));
                var download = await SendGetAsync<DownloadResultResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(upload.Uploaded, Is.True);
                    Assert.That(launch.JobId, Is.Not.EqualTo(Guid.Empty));
                    Assert.That(job.ScriptName, Is.EqualTo("RenderFramesCycles"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(job.ResultBlobId, Is.Null);
                    Assert.That(job.ResultBlobIds.Count, Is.EqualTo(3));
                    Assert.That(download.Downloaded, Is.True);
                    Assert.That(download.Items.Count, Is.EqualTo(3));
                    Assert.That(download.Items.All(me => me.FileName.EndsWith(".png", StringComparison.OrdinalIgnoreCase)), Is.True);
                    Assert.That(download.Items.All(me => me.FileSize > 0), Is.True);
                    Assert.That(download.Items.All(me => File.Exists(me.LocalPath)), Is.True);
                });
            }
            finally
            {
                DeleteTempDirectory(tempDir);
            }
        }

        [Test]
        public async Task RunRenderVideoGetJobAndDownloadResultThroughLocalRestBridgeAgainstLiveServerReturnsLocalFileTest()
        {
            var solutionRoot = FindSolutionRoot();
            if (solutionRoot == null)
                Assert.Ignore("Solution root not found.");

            var scenePath = Path.Combine(solutionRoot, "@Data", "greasepencil-bike.blend");
            if (!File.Exists(scenePath))
                Assert.Ignore($"Bike scene not found at {scenePath}");

            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17806/bridge/";

            try
            {
                await using var bridgeHost = new BridgeLocalHost(
                    BridgeLiveIntegrationSettings.IdentityUrl,
                    localRestUrl,
                    tempDir,
                    cloudConnectionService: m_cloudConnectionService,
                    serverUrl: BridgeLiveIntegrationSettings.ServerUrl);
                await bridgeHost.StartAsync();

                using var http = new HttpClient();
                var upload = await SendGetAsync<UploadBlendResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.UploadBlendAsync), scenePath);
                var launch = await SendPostAsync<RunRenderVideoResponse>(
                    http,
                    localRestUrl,
                    nameof(IBlenderBridgeChannel.RunRenderVideoAsync),
                    upload.BlobId,
                    4,
                    24,
                    CreateBikeFrameOptions(),
                    CreateDefaultVideoOptions());
                var job = await WaitForJobCompletionAsync(http, localRestUrl, launch.JobId, TimeSpan.FromMinutes(20), TimeSpan.FromSeconds(2));
                var download = await SendGetAsync<DownloadResultResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(upload.Uploaded, Is.True);
                    Assert.That(launch.JobId, Is.Not.EqualTo(Guid.Empty));
                    Assert.That(job.ScriptName, Is.EqualTo("RenderVideoCycles"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(job.ResultBlobId, Is.Not.Null.And.Not.EqualTo(Guid.Empty));
                    Assert.That(download.Downloaded, Is.True);
                    Assert.That(download.Items, Has.Count.EqualTo(1));
                    Assert.That(download.FileName, Does.EndWith(".mp4"));
                    Assert.That(download.FileSize, Is.GreaterThan(1024));
                    Assert.That(File.Exists(download.LocalPath), Is.True);
                });
            }
            finally
            {
                DeleteTempDirectory(tempDir);
            }
        }

        #endregion

        #region Tools

        private static async Task<GetJobResponse> WaitForJobCompletionAsync(HttpClient http, string localRestUrl, Guid jobId, TimeSpan timeout, TimeSpan pollInterval)
        {
            var startedUtc = DateTime.UtcNow;
            var observedIncompleteState = false;
            string? lastStatus = null;
            double? lastProgress = null;
            int? lastResultCount = null;

            while (DateTime.UtcNow - startedUtc < timeout)
            {
                var job = await SendGetAsync<GetJobResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.GetJobAsync), jobId.ToString());
                var currentResultCount = job.ResultBlobIds?.Count ?? 0;
                if (!string.Equals(lastStatus, job.Status, StringComparison.Ordinal)
                    || lastProgress != job.OverallProgress
                    || lastResultCount != currentResultCount)
                {
                    TestContext.Progress.WriteLine(
                        $"Bridge job {jobId}: Status={job.Status}; IsCompleted={job.IsCompleted}; Progress={job.OverallProgress:F3}; ResultBlobId={job.ResultBlobId}; ResultBlobIds={currentResultCount}; Error={job.ErrorMessage ?? "none"}");
                    lastStatus = job.Status;
                    lastProgress = job.OverallProgress;
                    lastResultCount = currentResultCount;
                }

                if (string.Equals(job.Status, ProcessingJobStatus.Failed.ToString(), StringComparison.OrdinalIgnoreCase))
                {
                    if (!string.IsNullOrWhiteSpace(job.ErrorMessage)
                        && job.ErrorMessage.Contains("No fallback nodes available", StringComparison.OrdinalIgnoreCase))
                    {
                        Assert.Ignore($"Live bridge integration skipped because deployed render capacity is currently unavailable: {job.ErrorMessage}");
                    }

                    Assert.Fail($"Bridge job {jobId} failed: {job.ErrorMessage}");
                }

                if (!job.IsCompleted)
                {
                    observedIncompleteState = true;
                    Assert.That(job.OverallProgress, Is.LessThan(100d),
                        "Bridge reported 100% overall progress before the job reached Completed.");
                }
                else
                {
                    Assert.That(job.Status, Is.EqualTo("Completed"), job.ErrorMessage);
                    return job;
                }

                await Task.Delay(pollInterval);
            }

            var finalJob = await SendGetAsync<GetJobResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.GetJobAsync), jobId.ToString());
            if (!string.IsNullOrWhiteSpace(finalJob.ErrorMessage)
                && finalJob.ErrorMessage.Contains("No fallback nodes available", StringComparison.OrdinalIgnoreCase))
            {
                Assert.Ignore($"Live bridge integration skipped because deployed render capacity is currently unavailable: {finalJob.ErrorMessage}");
            }

            Assert.Fail($"Bridge job {jobId} did not complete within {timeout}. ObservedIncompleteState={observedIncompleteState}");
            return null!;
        }

        private static RenderOptionsData CreateStillOptions()
        {
            return new RenderOptionsData
            {
                Format = RenderFormat.PNG,
                Engine = RenderEngine.Cycles,
                Samples = 4,
                ResolutionX = 64,
                ResolutionY = 64
            };
        }

        private static RenderOptionsData CreateCubeDioramaOptions()
        {
            return new RenderOptionsData
            {
                Format = RenderFormat.PNG,
                Engine = RenderEngine.Cycles,
                Samples = 0,
                ResolutionX = 2048,
                ResolutionY = 2048
            };
        }

        private static RenderOptionsData CreateBikeFrameOptions()
        {
            return new RenderOptionsData
            {
                Format = RenderFormat.PNG,
                Engine = RenderEngine.Cycles,
                Samples = 1,
                ResolutionX = 640,
                ResolutionY = 360
            };
        }

        private static TileOptionsData CreateDefaultAddonTileOptions()
        {
            return new TileOptionsData
            {
                OverlapPx = 8,
                BlendMode = TileBlendMode.CenterPriorityCrop
            };
        }

        private static VideoOptionsData CreateDefaultVideoOptions()
        {
            return new VideoOptionsData
            {
                FrameRate = 24,
                ConstantRateFactor = 23
            };
        }

        private static string? FindSolutionRoot()
        {
            var directory = TestContext.CurrentContext.TestDirectory;
            while (directory != null)
            {
                if (File.Exists(Path.Combine(directory, "OutWit.slnx")))
                    return directory;

                directory = Path.GetDirectoryName(directory);
            }

            return null;
        }

        #endregion
    }
}
