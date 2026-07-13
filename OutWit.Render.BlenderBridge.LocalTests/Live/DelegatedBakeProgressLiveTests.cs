using OutWit.Cloud.Data.Processing;
using OutWit.Controller.Render.Model;

namespace OutWit.Render.BlenderBridge.LocalTests.Live
{
    /// <summary>
    /// Live proof of the activity-progress sink: during a delegated fluid bake the job's
    /// <c>OverallProgress</c> must MOVE (the node streams per-frame OUTWIT_BAKE_PROGRESS →
    /// NodeActivityProgress → the server interpolates within the current stage), where before the sink it
    /// froze for the entire bake. The distributed per-frame channel must stay intact: once frames render,
    /// <c>DistributedProgress</c> advances exactly as before (it is fed by the untouched
    /// NodeTaskProgress.CompletedCount path — the addon's second progress bar).
    ///
    /// Requires the deployed witcloud 1.6.66+ (server sink) AND node clients 1.1.2-beta+ (event
    /// subscription). [Explicit] + env-gated on OMNIBUSCLOUD_API_KEY; needs @Data/lava_sim.blend.
    /// </summary>
    [TestFixture]
    [Explicit("Live progress proof against the deployed OmnibusCloud instance — samples job progress during a delegated bake.")]
    [NonParallelizable]
    internal sealed class DelegatedBakeProgressLiveTests
    {
        #region Constants

        private static readonly TimeSpan TIMEOUT = TimeSpan.FromMinutes(30);
        private static readonly TimeSpan SAMPLE_INTERVAL = TimeSpan.FromSeconds(2);

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
        public async Task OverallProgressMovesDuringTheDelegatedBakeLiveTest()
        {
            var scenePath = TestPaths.ResolveScene("lava_sim.blend", "lava_sim.blend");

            using var cts = new CancellationTokenSource(TIMEOUT);
            var client = await m_connection.GetClientAsync(cts.Token);
            Assert.That(client, Is.Not.Null, "live SDK client must be connected");

            var blobId = await client!.Blobs.UploadBlobFromFileAsync(scenePath, ct: cts.Token);
            var scene = new RenderSceneRefData { BlendBlobId = blobId, AttachedFiles = [] };

            var renderOptions = new RenderOptionsData
            {
                Engine = RenderEngine.Cycles,
                ResolutionX = 640,
                ResolutionY = 360,
                Samples = 16,
                Format = RenderFormat.PNG
            };
            var video = new VideoOptionsData { FrameRate = 24, ConstantRateFactor = 22 };

            var handle = await client.Scripts.RunAsync(
                "BakeAndRenderVideoCycles", scene, 46, 95, renderOptions, new RenderBakeOptionsData(), video, cts.Token);

            TestContext.Progress.WriteLine($"JobId={handle.JobId} — sampling Overall/Distributed progress every {SAMPLE_INTERVAL.TotalSeconds:0}s.");

            // Sample both progress channels until the job reaches a terminal state.
            var samples = new List<(TimeSpan Elapsed, ProcessingJobStatus Status, double Overall, double Distributed)>();
            var started = DateTime.UtcNow;
            ProcessingJobStatus status;
            do
            {
                await Task.Delay(SAMPLE_INTERVAL, cts.Token);
                var job = await client.Jobs.GetStatusAsync(handle.JobId, cts.Token);
                status = job.Status;
                samples.Add((DateTime.UtcNow - started, status, job.OverallProgress, job.DistributedProgress));

                var last = samples[^1];
                TestContext.Progress.WriteLine(
                    $"  t={last.Elapsed.TotalSeconds,6:0}s status={last.Status,-10} overall={last.Overall:0.000} distributed={last.Distributed:0.000}");
            }
            while (status is ProcessingJobStatus.Pending or ProcessingJobStatus.Processing && !cts.IsCancellationRequested);

            Assert.That(status, Is.EqualTo(ProcessingJobStatus.Completed), "the bake+render job must complete");

            // The BAKE PHASE = samples before the distributed (per-frame) channel first moves.
            var bakePhase = samples.TakeWhile(s => s.Distributed <= 0).ToList();
            var distinctOverallDuringBake = bakePhase.Select(s => Math.Round(s.Overall, 4)).Distinct().Count();

            TestContext.Progress.WriteLine(
                $"Bake-phase samples: {bakePhase.Count}; distinct OverallProgress values during bake: {distinctOverallDuringBake}.");

            Assert.Multiple(() =>
            {
                // THE sink proof: before this feature, OverallProgress held ONE value for the whole bake.
                Assert.That(distinctOverallDuringBake, Is.GreaterThanOrEqualTo(3),
                    "OverallProgress must move DURING the delegated bake (the activity-progress sink)");

                // The per-frame channel (the addon's second bar) must still work exactly as before.
                Assert.That(samples.Max(s => s.Distributed), Is.GreaterThan(0),
                    "DistributedProgress must advance during the distributed render phase (untouched NodeTaskProgress path)");

                // Monotonic: the interpolation must never regress the job's progress.
                for (var i = 1; i < samples.Count; i++)
                    Assert.That(samples[i].Overall, Is.GreaterThanOrEqualTo(samples[i - 1].Overall - 1e-9),
                        $"OverallProgress regressed at sample {i}");
            });
        }

        #endregion
    }
}
