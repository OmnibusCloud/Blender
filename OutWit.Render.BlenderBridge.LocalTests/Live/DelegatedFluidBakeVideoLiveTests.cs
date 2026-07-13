using OutWit.Cloud.Data.Processing;
using OutWit.Controller.Render.Model;

namespace OutWit.Render.BlenderBridge.LocalTests.Live
{
    /// <summary>
    /// F12 live proof + eyeball deliverable. The delegated FLUID bake used to no-op headless
    /// (<c>bpy.ops.fluid.bake_all()</c> is modal — it returned instantly, flipped the baked flag, and wrote
    /// no cache), so every distributed Mantaflow render came out EMPTY. The fix bakes via
    /// <c>cache_type='REPLAY'</c> + timeline stepping, which actually runs the solver headless. This fixture
    /// proves it end-to-end on real simulation scenes: it uploads an UNBAKED fluid sim, runs
    /// <c>BakeAndRenderVideoCycles</c> (bake on one delegated node → distribute the render → encode MP4), and
    /// downloads the video to <c>@Output/live/F12_sim_videos/</c> so the result can be inspected BY EYE — an
    /// empty (pre-fix) bake would render blank frames.
    ///
    /// Needs the deployed 1.23.16 render controller (the F12 fix). [Explicit] + env-gated on
    /// OMNIBUSCLOUD_API_KEY. Each scene lives in <c>@Data/</c> (gitignored, developer-supplied) and its test
    /// self-skips when the scene is absent. One test per scene so each renders (and is viewable) on its own.
    /// </summary>
    [TestFixture]
    [Explicit("F12 live proof — a delegated fluid bake renders a NON-EMPTY video; needs the deployed 1.23.16 controller.")]
    [NonParallelizable]
    internal sealed class DelegatedFluidBakeVideoLiveTests
    {
        #region Constants

        private static readonly TimeSpan TIMEOUT = TimeSpan.FromMinutes(40);

        #endregion

        #region Fields

        private LiveCloudConnectionService m_connection = null!;
        private string m_outputDir = null!;

        #endregion

        #region Setup

        [OneTimeSetUp]
        public async Task SetupAsync()
        {
            if (!LiveIntegrationSettings.IsConfigured)
                Assert.Ignore("Live integration skipped: set OMNIBUSCLOUD_API_KEY.");

            // One shared output folder for all three videos, created but NEVER wiped — so re-running a single
            // scene keeps the other scenes' videos (TestPaths.OutputDir() deletes the folder on each call).
            m_outputDir = Path.Combine(TestPaths.OutputRoot, "live", "F12_sim_videos");
            Directory.CreateDirectory(m_outputDir);

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

        // A viscous LIQUID (lava) — the user's own showcase example. Its glowing lava material + camera ship
        // with the demo; the sim starts at frame 46, so the bake fills 46..end contiguously.
        [Test]
        public Task LavaViscousLiquidBakesAndRendersNonEmptyVideoLiveTest() =>
            BakeAndRenderVideoAsync("lava_sim.blend", startFrame: 46, endFrame: 95, outName: "lava");

        // A plain FLIP water LIQUID.
        [Test]
        public Task FlipWaterLiquidBakesAndRendersNonEmptyVideoLiveTest() =>
            BakeAndRenderVideoAsync("fluid-simulation_flip_vs_apic_solver.blend", startFrame: 1, endFrame: 50, outName: "flip");

        // A GAS smoke domain — exercises the per-frame OpenVDB density slicing path (distinct from the
        // liquid mesh path), so each render node gets only its frame's density grid.
        [Test]
        public Task GasSmokeBakesAndRendersNonEmptyVideoLiveTest() =>
            BakeAndRenderVideoAsync("smoke_sim.blend", startFrame: 1, endFrame: 50, outName: "smoke");

        #endregion

        #region Tools

        private async Task BakeAndRenderVideoAsync(string sceneFile, int startFrame, int endFrame, string outName)
        {
            var scenePath = TestPaths.ResolveScene(sceneFile, sceneFile);

            using var cts = new CancellationTokenSource(TIMEOUT);
            var client = await m_connection.GetClientAsync(cts.Token);
            Assert.That(client, Is.Not.Null, "live SDK client must be connected");

            var blobId = await client!.Blobs.UploadBlobFromFileAsync(scenePath, ct: cts.Token);
            var scene = new RenderSceneRefData
            {
                BlendBlobId = blobId,
                AttachedFiles = new List<RenderSceneAttachmentRefData>()
            };

            var bakeOptions = new RenderBakeOptionsData();
            var renderOptions = new RenderOptionsData
            {
                Engine = RenderEngine.Cycles,
                ResolutionX = 640,
                ResolutionY = 360,
                Samples = 48,
                Format = RenderFormat.PNG
            };
            var video = new VideoOptionsData { FrameRate = 24, ConstantRateFactor = 20 };

            TestContext.Progress.WriteLine(
                $"F12 {outName}: delegated bake + distributed video render, frames {startFrame}-{endFrame} " +
                $"({Path.GetFileName(scenePath)}). A pre-fix (no-op) bake would render EMPTY frames.");

            var handle = await client.Scripts.RunAsync(
                "BakeAndRenderVideoCycles", scene, startFrame, endFrame, renderOptions, bakeOptions, video, cts.Token);

            TestContext.Progress.WriteLine($"JobId={handle.JobId} — bake runs on one delegated node, then the frames distribute.");

            var waitResult = await handle.WaitAsync<Guid>(pollInterval: TimeSpan.FromSeconds(10), ct: cts.Token);

            TestContext.Progress.WriteLine(
                $"Job {handle.JobId} finished: status={waitResult.Status}, duration={waitResult.Duration:hh\\:mm\\:ss}, error={waitResult.ErrorMessage}");

            Assert.That(waitResult.Status, Is.EqualTo(ProcessingJobStatus.Completed),
                $"the delegated fluid bake + render must complete. Error: {waitResult.ErrorMessage}");

            var blob = waitResult.Result;
            if (blob == Guid.Empty)
                blob = await handle.GetResultAsync<Guid>(ct: cts.Token);
            Assert.That(blob, Is.Not.EqualTo(Guid.Empty), "the bake-and-render-video job did not return a video blob.");

            var localPath = Path.Combine(m_outputDir, $"{outName}.mp4");
            await client.Blobs.DownloadBlobToFileAsync(blob, localPath, ct: cts.Token);

            Assert.That(File.Exists(localPath), Is.True, $"Downloaded video was not found at {localPath}");
            var size = new FileInfo(localPath).Length;
            // A real fluid video is many KB+; a near-empty MP4 would betray a bake that produced no cache.
            Assert.That(size, Is.GreaterThan(10_000),
                $"video is suspiciously small ({size} bytes) — the bake may have produced an empty simulation (F12 regression).");

            TestContext.Progress.WriteLine($"F12 {outName}: video saved to {localPath} ({size / 1024} KB) — open it to eyeball the sim.");
        }

        #endregion
    }
}
