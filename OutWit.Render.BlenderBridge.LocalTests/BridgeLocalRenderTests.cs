using System.Net.Http;
using OutWit.Cloud.Data.Processing;
using OutWit.Controller.Render.Model;
using OutWit.Render.BlenderBridge.Channels.Interfaces;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Tests.Infrastructure.Hosting;
using static OutWit.Render.BlenderBridge.Tests.Infrastructure.Transport.BridgeRestTestUtils;

namespace OutWit.Render.BlenderBridge.LocalTests
{
    /// <summary>
    /// Tier-B (local) render tests: the full bridge stack runs against the REAL render controller
    /// in-process via OutWit.Engine.Sdk — no WitCloud server, no online clients, no deploy cycle.
    /// Uses the controller's own bundled benchmark scenes (staged by the nuget package). Self-skips
    /// when no host Blender runtime is present (see <see cref="BridgeLocalRenderTestsBase"/>).
    /// </summary>
    [TestFixture]
    [NonParallelizable]
    internal sealed class BridgeLocalRenderTests : BridgeLocalRenderTestsBase
    {
        #region Constants

        private static readonly TimeSpan TIMEOUT = TimeSpan.FromMinutes(5);

        #endregion

        #region Tests

        [Test]
        public async Task UploadBlendAndRunRenderValidateBlendAgainstLocalEngineReturnsValidationResultTest()
        {
            var scenePath = BenchmarkScene("benchmark_scene_still.blend");
            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17821/bridge/";

            try
            {
                await using var bridgeHost = CreateBridgeHost(localRestUrl, tempDir);
                await bridgeHost.StartAsync();

                using var http = new HttpClient();
                var upload = await SendGetAsync<UploadBlendResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.UploadBlendAsync), scenePath);
                var validation = await SendGetAsync<RenderValidateBlendResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.RunRenderValidateBlendAsync), upload.BlobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(upload.Uploaded, Is.True);
                    Assert.That(validation.JobId, Is.Not.EqualTo(Guid.Empty));
                    Assert.That(validation.Completed, Is.True, validation.Message);
                    Assert.That(validation.IsValid, Is.True, string.Join("; ", validation.Issues ?? []));
                    Assert.That(validation.Status, Is.EqualTo("Completed"));
                });
            }
            finally
            {
                DeleteTempDirectory(tempDir);
            }
        }

        [Test]
        public async Task RunRenderStillGetJobAndDownloadResultAgainstLocalEngineReturnsLocalPngTest()
        {
            var scenePath = BenchmarkScene("benchmark_scene_still.blend");
            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17822/bridge/";

            try
            {
                await using var bridgeHost = CreateBridgeHost(localRestUrl, tempDir);
                await bridgeHost.StartAsync();

                using var http = new HttpClient();
                var upload = await SendGetAsync<UploadBlendResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.UploadBlendAsync), scenePath);
                var launch = await SendPostAsync<RunRenderStillResponse>(
                    http, localRestUrl, nameof(IBlenderBridgeChannel.RunRenderStillAsync),
                    upload.BlobId, 1, CreateOptions());
                var job = await WaitForJobCompletionAsync(http, localRestUrl, launch.JobId);
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
        public async Task RunRenderFramesGetJobAndDownloadResultAgainstLocalEngineReturnsLocalPngsTest()
        {
            var scenePath = BenchmarkScene("benchmark_scene_video.blend");
            var tempDir = CreateTempDirectory();
            const string localRestUrl = "http://127.0.0.1:17823/bridge/";

            try
            {
                await using var bridgeHost = CreateBridgeHost(localRestUrl, tempDir);
                await bridgeHost.StartAsync();

                using var http = new HttpClient();
                var upload = await SendGetAsync<UploadBlendResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.UploadBlendAsync), scenePath);
                var launch = await SendPostAsync<RunRenderFramesResponse>(
                    http, localRestUrl, nameof(IBlenderBridgeChannel.RunRenderFramesAsync),
                    upload.BlobId, 1, 2, CreateOptions());
                var job = await WaitForJobCompletionAsync(http, localRestUrl, launch.JobId);
                var download = await SendGetAsync<DownloadResultResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(upload.Uploaded, Is.True);
                    Assert.That(job.ScriptName, Is.EqualTo("RenderFramesCycles"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(job.ResultBlobIds, Has.Count.EqualTo(2));
                    Assert.That(download.Downloaded, Is.True);
                    Assert.That(download.Items, Has.Count.EqualTo(2));
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

        #endregion

        #region Tools

        private static string BenchmarkScene(string fileName)
        {
            var path = Path.Combine(AppContext.BaseDirectory, "@Controllers", "render.module", fileName);
            if (!File.Exists(path))
                Assert.Ignore($"Bundled benchmark scene '{fileName}' not staged at '{path}'.");

            return path;
        }

        private static RenderOptionsData CreateOptions()
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

        private static async Task<GetJobResponse> WaitForJobCompletionAsync(HttpClient http, string localRestUrl, Guid jobId)
        {
            var started = DateTime.UtcNow;
            while (DateTime.UtcNow - started < TIMEOUT)
            {
                var job = await SendGetAsync<GetJobResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.GetJobAsync), jobId.ToString());

                if (string.Equals(job.Status, ProcessingJobStatus.Failed.ToString(), StringComparison.OrdinalIgnoreCase))
                    Assert.Fail($"Local job {jobId} failed: {job.ErrorMessage}");

                if (job.IsCompleted)
                    return job;

                await Task.Delay(TimeSpan.FromMilliseconds(250));
            }

            Assert.Fail($"Local job {jobId} did not complete within {TIMEOUT}.");
            return null!;
        }

        private static string CreateTempDirectory()
        {
            var path = Path.Combine(Path.GetTempPath(), "BridgeLocalRenderTests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(path);
            return path;
        }

        private static void DeleteTempDirectory(string path)
        {
            if (!Directory.Exists(path))
                return;

            try { Directory.Delete(path, recursive: true); }
            catch { /* best-effort */ }
        }

        #endregion
    }
}
