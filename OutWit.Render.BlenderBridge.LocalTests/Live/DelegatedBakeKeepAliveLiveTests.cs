using OutWit.Cloud.Data.Processing;
using OutWit.Controller.Render.Model;

namespace OutWit.Render.BlenderBridge.LocalTests.Live
{
    /// <summary>
    /// F11 live proof: a delegated simulation bake that runs WELL PAST the old 5-minute per-task budget
    /// must now survive and complete on a healthy fleet.
    ///
    /// Before F11, <c>Render.BakeSimulation</c> was delivered to a node as a single-task batch whose
    /// server budget was <c>TaskTimeout × 1 = 5 minutes</c>. A real bake exceeds that, so the server
    /// settled the batch <c>TimedOut</c> mid-bake, killed Blender, re-dispatched to a second healthy node,
    /// and ultimately failed the job — the exact symptom this test reproduces. With F11 the worker keeps
    /// the job alive with progress pings while it bakes (the batch is reaped only after a full window of
    /// SILENCE), and the controller caps a genuinely wedged bake at 4 h, so a long bake now completes.
    ///
    /// The workload is a heavy CLOTH simulation, deliberately chosen over a Mantaflow fluid: cloth bakes
    /// via Blender's POINT CACHE (<c>ptcache.bake_all</c>), which — unlike the modal <c>fluid.bake_all</c> —
    /// does real, non-modal, per-frame work headless, so the bake time is predictable and reproducible. The
    /// scene (self-collided pressure cloth, quality 25, ~13.7 k verts over 350 frames) bakes for ~7 minutes
    /// on a single delegated node; the point-cache travels EMBEDDED in the baked blend, and the STILL script
    /// renders only ONE cheap frame afterwards, so the wall clock is the BAKE, not the distributed render.
    /// THIS RUN WOULD FAIL WITHOUT F11.
    ///
    /// [Explicit] + env-gated on OMNIBUSCLOUD_API_KEY. Requires <c>@Data/cloth_heavy_bake.blend</c>
    /// (gitignored, developer-supplied — a heavy point-cache sim, camera-framed and render-ready); the test
    /// self-skips without it.
    /// </summary>
    [TestFixture]
    [Explicit("F11 live proof against the deployed OmnibusCloud instance — a >5-minute delegated bake that used to time out.")]
    [NonParallelizable]
    internal sealed class DelegatedBakeKeepAliveLiveTests
    {
        #region Constants

        private static readonly TimeSpan TIMEOUT = TimeSpan.FromMinutes(45);
        private static readonly TimeSpan OLD_TASK_BUDGET = TimeSpan.FromMinutes(5);

        #endregion

        #region Fields

        private LiveCloudConnectionService m_connection = null!;

        #endregion

        #region Setup

        [OneTimeSetUp]
        public async Task SetupAsync()
        {
            if (!LiveIntegrationSettings.IsConfigured)
                Assert.Ignore("Live integration skipped: set OMNIBUSCLOUD_API_KEY.");

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
        public async Task DelegatedBakeExceedingTheOldFiveMinuteBudgetSurvivesAndCompletesLiveTest()
        {
            // A heavy UNBAKED cloth sim: self-collided pressure cloth (~13.7 k verts, quality 25) baked over
            // 350 frames via the non-modal point-cache path. Render.BakeSimulation frees any stale cache and
            // re-bakes the whole contiguous range — ~7 minutes of real work on one delegated node. The STILL
            // script renders only ONE cheap frame afterwards, so the wall clock is the BAKE, not the render.
            var scenePath = TestPaths.ResolveScene("cloth_heavy_bake.blend", "cloth_heavy_bake.blend");

            using var cts = new CancellationTokenSource(TIMEOUT);
            var client = await m_connection.GetClientAsync(cts.Token);
            Assert.That(client, Is.Not.Null, "live SDK client must be connected");

            var blobId = await client!.Blobs.UploadBlobFromFileAsync(scenePath, ct: cts.Token);
            var scene = new RenderSceneRefData
            {
                BlendBlobId = blobId,
                AttachedFiles = new List<RenderSceneAttachmentRefData>()
            };

            const int frame = 200; // render a frame inside the baked 1..350 cloth cache

            // Cloth bakes through the point-cache path; ResolutionMax (fluid-only) is irrelevant here.
            var bakeOptions = new RenderBakeOptionsData();

            var renderOptions = new RenderOptionsData
            {
                Engine = RenderEngine.Cycles,
                ResolutionX = 640,
                ResolutionY = 360,
                Samples = 16,
                Format = RenderFormat.PNG
            };

            TestContext.Progress.WriteLine(
                $"Submitting long delegated bake: {Path.GetFileName(scenePath)} bake→still at frame {frame}, heavy self-collided cloth over 350 frames (this bake exceeds 5 min and would time out before F11).");

            var handle = await client.Scripts.RunAsync(
                "BakeAndRenderStillCycles", scene, frame, renderOptions, bakeOptions, cts.Token);

            TestContext.Progress.WriteLine($"JobId={handle.JobId} — watch NODE ASSIGNMENTS; the bake runs on one delegated node for minutes.");

            var waitResult = await handle.WaitAsync<Guid>(pollInterval: TimeSpan.FromSeconds(10), ct: cts.Token);

            TestContext.Progress.WriteLine(
                $"Job {handle.JobId} finished: status={waitResult.Status}, duration={waitResult.Duration:hh\\:mm\\:ss}, error={waitResult.ErrorMessage}");

            Assert.Multiple(() =>
            {
                Assert.That(waitResult.Status, Is.EqualTo(ProcessingJobStatus.Completed),
                    $"the delegated bake must complete — before F11 it was reaped at the 5-minute budget and failed. Error: {waitResult.ErrorMessage}");
                Assert.That(waitResult.Duration, Is.GreaterThan(OLD_TASK_BUDGET),
                    "the run must exceed the old 5-minute per-task budget to actually exercise F11; if it finished faster, raise the cloth cache frame_end or its simulation quality in @Data/cloth_heavy_bake.blend.");
            });

            var resultBlobId = waitResult.Result;
            if (resultBlobId == Guid.Empty)
                resultBlobId = await handle.GetResultAsync<Guid>(ct: cts.Token);

            Assert.That(resultBlobId, Is.Not.EqualTo(Guid.Empty), "the bake-and-render job did not return a result image blob.");

            var outputDir = TestPaths.OutputDir("live", nameof(DelegatedBakeExceedingTheOldFiveMinuteBudgetSurvivesAndCompletesLiveTest));
            var localPath = Path.Combine(outputDir, "cloth-delegated-bake.png");
            await client.Blobs.DownloadBlobToFileAsync(resultBlobId, localPath, ct: cts.Token);

            Assert.That(File.Exists(localPath), Is.True, $"Downloaded result image was not found at {localPath}");
            Assert.That(new FileInfo(localPath).Length, Is.GreaterThan(0), "Downloaded result image is empty.");
            TestContext.Progress.WriteLine($"Result image saved to: {localPath}");
        }

        #endregion
    }
}
