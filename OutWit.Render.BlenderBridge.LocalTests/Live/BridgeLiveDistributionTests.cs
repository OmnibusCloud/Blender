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
    /// Live (Tier-A) distribution tests with NON-trivial workloads against the deployed OmnibusCloud
    /// instance, intended for eyeballing load-balancing across worker nodes in the admin UI
    /// (NODE ASSIGNMENTS). Each test logs the JobId immediately after submit so it can be located in
    /// the UI while the render is still running. Uses the real WitEngine assets dropped into @Data:
    ///   - greasepencil-bike.blend : a long frame range (frames spread across nodes)
    ///   - cube_diorama.blend       : a large 2048² tiled still (tiles spread across nodes)
    /// [Explicit] + env-gated on OMNIBUSCLOUD_API_KEY. Long timeout — real multi-frame renders.
    /// </summary>
    [TestFixture]
    [Explicit("Live distribution workload against the deployed OmnibusCloud instance — watch NODE ASSIGNMENTS in the UI.")]
    [NonParallelizable]
    internal sealed class BridgeLiveDistributionTests
    {
        #region Constants

        private static readonly TimeSpan TIMEOUT = TimeSpan.FromMinutes(40);
        private static readonly TimeSpan POLL = TimeSpan.FromSeconds(5);

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
        public async Task FramesDistributedAcrossNodesLiveTest()
        {
            // greasepencil-bike has a long timeline; 1..120 gives the balancer something real to split.
            const int startFrame = 1;
            const int endFrame = 120;

            var scenePath = TestPaths.ResolveScene("benchmark_scene_video.blend", "greasepencil-bike.blend");
            await RunBridgeAsync(17861, async (http, url, outputDir) =>
            {
                var upload = await UploadAsync(http, url, scenePath);
                var launch = await SendPostAsync<RunRenderFramesResponse>(
                    http, url, nameof(IBlenderBridgeChannel.RunRenderFramesAsync),
                    upload.BlobId, startFrame, endFrame, FrameOptions());

                Banner($"FRAMES submitted: JobId={launch.JobId}  ({endFrame - startFrame + 1} frames) — open NODE ASSIGNMENTS in the UI now");

                var job = await WaitForJobCompletionAsync(http, url, launch.JobId);
                var download = await SendGetAsync<DownloadResultResponse>(http, url, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(job.ScriptName, Is.EqualTo("RenderFramesCycles"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(job.ResultBlobIds, Has.Count.EqualTo(endFrame - startFrame + 1));
                    Assert.That(download.Items.All(me => me.FileSize > 0), Is.True);
                });
                TestContext.Progress.WriteLine($"FRAMES done: {download.Items.Count} files in {outputDir}");
            });
        }

        [Test]
        public async Task FramesTargetedAtClientGroupLiveTest()
        {
            // The crowdcomputing portal's MAIN flow: submit a render to ONE client group instead of "all
            // clients". Group id comes from OMNIBUSCLOUD_GROUP_ID, else the operator's two-machine test
            // group. Asserts the group-targeted submit reaches a group with capable clients and the job
            // completes; watch NODE ASSIGNMENTS in the UI to confirm it ran on that group's machines only.
            var groupId = ResolveGroupId();
            const int startFrame = 1;
            const int endFrame = 20;

            var scenePath = TestPaths.ResolveScene("benchmark_scene_video.blend", "greasepencil-bike.blend");
            await RunBridgeAsync(17871, async (http, url, outputDir) =>
            {
                var upload = await UploadAsync(http, url, scenePath);

                // 6-param overload = the group-targeted RunRenderFrames (blob, start, end, options,
                // attachments, groupId). The REST processor binds by exact arity.
                var launch = await SendPostAsync<RunRenderFramesResponse>(
                    http, url, nameof(IBlenderBridgeChannel.RunRenderFramesAsync),
                    upload.BlobId, startFrame, endFrame, FrameOptions(),
                    new List<RenderSceneAttachmentRefData>(), groupId);

                Banner($"GROUP FRAMES submitted: JobId={launch.JobId} -> group {groupId} ({endFrame - startFrame + 1} frames) — open NODE ASSIGNMENTS to confirm it ran on that group's machines");

                var job = await WaitForJobCompletionAsync(http, url, launch.JobId);

                Assert.Multiple(() =>
                {
                    Assert.That(job.Status, Is.EqualTo("Completed"), "group-targeted render must complete on the group's clients");
                    Assert.That(job.ResultBlobIds, Has.Count.EqualTo(endFrame - startFrame + 1));
                });
                TestContext.Progress.WriteLine($"GROUP FRAMES done on group {groupId}: {job.ResultBlobIds.Count} frames in {outputDir}");
            });
        }

        [Test]
        public async Task ApiKeyUserExecutionScopeDiagnosticsLiveTest()
        {
            // Read-only: prints the execution scope the OMNIBUSCLOUD_API_KEY user actually has, so a
            // group-submit "not authorized" failure can be traced to either (a) no scope / no group
            // grant, or (b) the wrong group id in the test vs the groups the api-key user can target.
            var client = await m_connection.GetClientAsync();
            Assert.That(client, Is.Not.Null, "live SDK client must be connected");

            var scope = await client!.GetExecutionScopeOptionsAsync();

            Banner($"API-KEY USER SCOPE: CanRunOnAllClients={scope.CanRunOnAllClients}, Groups={scope.Groups.Length}, Projects={scope.Projects.Length}");
            foreach (var group in scope.Groups)
                TestContext.Progress.WriteLine($"  authorized group: {group.GroupId}  '{group.Name}'");

            var target = ResolveGroupId();
            var allowed = scope.CanRunOnAllClients || scope.Groups.Any(me => me.GroupId == target);
            TestContext.Progress.WriteLine($"  -> can target test group {target}: {allowed}");
        }

        [Test]
        public async Task FramesGroupSubmitViaSdkDirectLiveTest()
        {
            // ISOLATION: bypass the bridge REST layer entirely. Replicate the bridge's group path SDK
            // call (BridgeRenderLaunchService.RunRenderFramesAsync group branch) DIRECTLY against the
            // live server via the public SDK, so the real server/SDK reason surfaces — the bridge REST
            // processor otherwise masks it as a bare "Failed to process request".
            //   - submit ACCEPTED  -> server+SDK group submit works; the bug is in the bridge REST 6-param routing.
            //   - submit THROWS    -> ex.Message is the real server rejection (eligibility / script / params).
            var groupId = ResolveGroupId();
            const int startFrame = 1;
            const int endFrame = 20;

            var scenePath = TestPaths.ResolveScene("benchmark_scene_video.blend", "greasepencil-bike.blend");
            await RunBridgeAsync(17873, async (http, url, outputDir) =>
            {
                // Upload via the proven bridge path (upload is not the suspect — the all-clients tests use it).
                var upload = await UploadAsync(http, url, scenePath);

                var client = await m_connection.GetClientAsync();
                Assert.That(client, Is.Not.Null, "live SDK client must be connected");

                var scene = new RenderSceneRefData
                {
                    BlendBlobId = upload.BlobId,
                    AttachedFiles = new List<RenderSceneAttachmentRefData>()
                };

                // EXACT replica of the bridge group branch:
                //   client.Scripts.SubmitAsync(scriptName, new object?[]{ scene, start, end, options }, groupId)
                Guid jobId;
                try
                {
                    var handle = await client!.Scripts.SubmitAsync(
                        "RenderFramesCycles",
                        new object?[] { scene, startFrame, endFrame, FrameOptions() },
                        groupId);
                    jobId = handle.JobId;
                }
                catch (Exception ex)
                {
                    // The real server/SDK rejection — NOT masked by the bridge REST processor.
                    Banner($"SDK-DIRECT GROUP submit FAILED at SDK level: {ex.GetType().Name}: {ex.Message}");
                    throw;
                }

                Banner($"SDK-DIRECT GROUP submit ACCEPTED: JobId={jobId} -> group {groupId} — server accepted the group-targeted submission");

                var job = await WaitForJobCompletionAsync(http, url, jobId);
                Assert.That(job.Status, Is.EqualTo("Completed"), "group-targeted render must complete on the group's clients");
                Assert.That(job.ResultBlobIds, Has.Count.EqualTo(endFrame - startFrame + 1));
                TestContext.Progress.WriteLine($"SDK-DIRECT GROUP done on group {groupId}: {job.ResultBlobIds.Count} frames in {outputDir}");
            });
        }

        private static Guid ResolveGroupId()
        {
            var raw = Environment.GetEnvironmentVariable("OMNIBUSCLOUD_GROUP_ID");
            if (!string.IsNullOrWhiteSpace(raw) && Guid.TryParse(raw, out var fromEnv))
                return fromEnv;

            // Default: the operator's two-machine crowdcomputing test group.
            return Guid.Parse("b952dfd2-3483-4fe0-a266-c584cd13f591");
        }

        [Test]
        public async Task FramesEeveeDistributedAcrossNodesLiveTest()
        {
            // Eevee frames through the persistent-batch CLI animation render (-a) — the macOS-safe path
            // (1.18.2). The original live failure was Cycles-only; this proves the second engine.
            const int startFrame = 1;
            const int endFrame = 24;

            var scenePath = TestPaths.ResolveScene("benchmark_scene_video.blend", "greasepencil-bike.blend");
            await RunBridgeAsync(17865, async (http, url, outputDir) =>
            {
                var upload = await UploadAsync(http, url, scenePath);
                var launch = await SendPostAsync<RunRenderFramesResponse>(
                    http, url, nameof(IBlenderBridgeChannel.RunRenderFramesAsync),
                    upload.BlobId, startFrame, endFrame, EeveeFrameOptions());

                Banner($"EEVEE FRAMES submitted: JobId={launch.JobId}  ({endFrame - startFrame + 1} frames) — open NODE ASSIGNMENTS");

                var job = await WaitForJobCompletionAsync(http, url, launch.JobId);
                var download = await SendGetAsync<DownloadResultResponse>(http, url, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(job.ScriptName, Is.EqualTo("RenderFramesEevee"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(job.ResultBlobIds, Has.Count.EqualTo(endFrame - startFrame + 1));
                    Assert.That(download.Items.All(me => me.FileSize > 0), Is.True);
                });
                TestContext.Progress.WriteLine($"EEVEE FRAMES done: {download.Items.Count} files in {outputDir}");
            });
        }

        [Test]
        public async Task FramesGreasePencilDistributedAcrossNodesLiveTest()
        {
            // Grease Pencil frames (rendered via Eevee Next) — confirms the third engine on the CLI -a path.
            const int startFrame = 1;
            const int endFrame = 24;

            var scenePath = TestPaths.ResolveScene("benchmark_scene_video.blend", "greasepencil-bike.blend");
            await RunBridgeAsync(17867, async (http, url, outputDir) =>
            {
                var upload = await UploadAsync(http, url, scenePath);
                var launch = await SendPostAsync<RunRenderFramesResponse>(
                    http, url, nameof(IBlenderBridgeChannel.RunRenderFramesAsync),
                    upload.BlobId, startFrame, endFrame, GreasePencilFrameOptions());

                Banner($"GREASE PENCIL FRAMES submitted: JobId={launch.JobId}  ({endFrame - startFrame + 1} frames) — open NODE ASSIGNMENTS");

                var job = await WaitForJobCompletionAsync(http, url, launch.JobId);
                var download = await SendGetAsync<DownloadResultResponse>(http, url, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(job.ScriptName, Is.EqualTo("RenderFramesGreasePencil"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(job.ResultBlobIds, Has.Count.EqualTo(endFrame - startFrame + 1));
                    Assert.That(download.Items.All(me => me.FileSize > 0), Is.True);
                });
                TestContext.Progress.WriteLine($"GREASE PENCIL FRAMES done: {download.Items.Count} files in {outputDir}");
            });
        }

        [Test]
        public async Task LargeScaleCyclesFramesDistributedAcrossNodesLiveTest()
        {
            // Render-bound regime: 1080p / 128 spp. With 64 frames the Cycles chunk = ceil(64/48)=2, so
            // persistent-batch is active. This is the scale where balance was historically good — render
            // time per frame dominates the fixed per-frame overhead, so node Rate predicts real wall.
            const int startFrame = 1;
            const int endFrame = 64;

            var scenePath = TestPaths.ResolveScene("benchmark_scene_video.blend", "greasepencil-bike.blend");
            await RunBridgeAsync(17869, async (http, url, outputDir) =>
            {
                var upload = await UploadAsync(http, url, scenePath);
                var launch = await SendPostAsync<RunRenderFramesResponse>(
                    http, url, nameof(IBlenderBridgeChannel.RunRenderFramesAsync),
                    upload.BlobId, startFrame, endFrame, LargeCyclesFrameOptions());

                Banner($"LARGE CYCLES 1080p/128spp submitted: JobId={launch.JobId}  ({endFrame - startFrame + 1} frames) — open NODE ASSIGNMENTS");

                var job = await WaitForJobCompletionAsync(http, url, launch.JobId);
                var download = await SendGetAsync<DownloadResultResponse>(http, url, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(job.ScriptName, Is.EqualTo("RenderFramesCycles"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(job.ResultBlobIds, Has.Count.EqualTo(endFrame - startFrame + 1));
                    Assert.That(download.Items.All(me => me.FileSize > 0), Is.True);
                });
                TestContext.Progress.WriteLine($"LARGE CYCLES done: {download.Items.Count} files in {outputDir}");
            });
        }

        [Test]
        public async Task LargeScaleEeveeFramesDistributedAcrossNodesLiveTest()
        {
            // Overhead-bound engine at scale: 1080p / 64 spp Eevee. With 64 frames the Eevee chunk =
            // ceil(64/8)=8 (max), so persistent-batch amortises scene-load across 8 frames per process —
            // the case batching is meant to fix. Compare node wall here vs the chunk=1 small-scale skew.
            const int startFrame = 1;
            const int endFrame = 64;

            var scenePath = TestPaths.ResolveScene("benchmark_scene_video.blend", "greasepencil-bike.blend");
            await RunBridgeAsync(17871, async (http, url, outputDir) =>
            {
                var upload = await UploadAsync(http, url, scenePath);
                var launch = await SendPostAsync<RunRenderFramesResponse>(
                    http, url, nameof(IBlenderBridgeChannel.RunRenderFramesAsync),
                    upload.BlobId, startFrame, endFrame, LargeEeveeFrameOptions());

                Banner($"LARGE EEVEE 1080p/64spp submitted: JobId={launch.JobId}  ({endFrame - startFrame + 1} frames) — open NODE ASSIGNMENTS");

                var job = await WaitForJobCompletionAsync(http, url, launch.JobId);
                var download = await SendGetAsync<DownloadResultResponse>(http, url, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(job.ScriptName, Is.EqualTo("RenderFramesEevee"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(job.ResultBlobIds, Has.Count.EqualTo(endFrame - startFrame + 1));
                    Assert.That(download.Items.All(me => me.FileSize > 0), Is.True);
                });
                TestContext.Progress.WriteLine($"LARGE EEVEE done: {download.Items.Count} files in {outputDir}");
            });
        }

        [Test]
        public async Task ComputeBoundFramesDistributedAcrossNodesLiveTest()
        {
            // Heavy Cycles frames (512²/128 spp) — compute-bound, matching the benchmark's calibration
            // so node Rate becomes predictive. cube_diorama is a real 3D scene. With Norav stopped this
            // runs on the two free nodes (Mac M4 + ubuntu 1080 Ti) for a clean balancing comparison.
            const int startFrame = 1;
            const int endFrame = 30;

            var scenePath = TestPaths.ResolveScene("benchmark_scene_still.blend", "cube_diorama/cube_diorama.blend");
            await RunBridgeAsync(17863, async (http, url, outputDir) =>
            {
                var upload = await UploadAsync(http, url, scenePath);
                var launch = await SendPostAsync<RunRenderFramesResponse>(
                    http, url, nameof(IBlenderBridgeChannel.RunRenderFramesAsync),
                    upload.BlobId, startFrame, endFrame, HeavyFrameOptions());

                Banner($"COMPUTE-BOUND FRAMES submitted: JobId={launch.JobId}  ({endFrame - startFrame + 1} frames @512²/128spp) — open NODE ASSIGNMENTS");

                var job = await WaitForJobCompletionAsync(http, url, launch.JobId);
                var download = await SendGetAsync<DownloadResultResponse>(http, url, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(job.ScriptName, Is.EqualTo("RenderFramesCycles"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(job.ResultBlobIds, Has.Count.EqualTo(endFrame - startFrame + 1));
                    Assert.That(download.Items.All(me => me.FileSize > 0), Is.True);
                });
                TestContext.Progress.WriteLine($"COMPUTE-BOUND FRAMES done: {download.Items.Count} files in {outputDir}");
            });
        }

        [Test]
        public async Task TiledStillDistributedAcrossNodesLiveTest()
        {
            // 2048² cube_diorama split into a 4x4 = 16 tile grid → 16 render tasks for the balancer.
            const int tilesX = 4;
            const int tilesY = 4;

            var scenePath = TestPaths.ResolveScene("benchmark_scene_still.blend", "cube_diorama/cube_diorama.blend");
            await RunBridgeAsync(17862, async (http, url, outputDir) =>
            {
                var upload = await UploadAsync(http, url, scenePath);
                var launch = await SendPostAsync<RunRenderStillTiledResponse>(
                    http, url, nameof(IBlenderBridgeChannel.RunRenderStillTiledAsync),
                    upload.BlobId, 1, tilesX, tilesY, TiledOptions(), Tiles());

                Banner($"TILED submitted: JobId={launch.JobId}  ({tilesX}x{tilesY}={tilesX * tilesY} tiles @2048²) — open NODE ASSIGNMENTS in the UI now");

                var job = await WaitForJobCompletionAsync(http, url, launch.JobId);
                var download = await SendGetAsync<DownloadResultResponse>(http, url, nameof(IBlenderBridgeChannel.DownloadResultAsync), launch.JobId.ToString());

                Assert.Multiple(() =>
                {
                    Assert.That(job.ScriptName, Is.EqualTo("RenderStillTiledCycles"));
                    Assert.That(job.Status, Is.EqualTo("Completed"));
                    Assert.That(download.Items, Has.Count.EqualTo(1));
                    Assert.That(download.FileName, Does.EndWith(".png"));
                    Assert.That(download.FileSize, Is.GreaterThan(0));
                });
                TestContext.Progress.WriteLine($"TILED done: {download.FileName} ({download.FileSize} bytes) in {outputDir}");
            });
        }

        #endregion

        #region Tools

        private async Task RunBridgeAsync(int port, Func<HttpClient, string, string, Task> body, [System.Runtime.CompilerServices.CallerMemberName] string testName = "")
        {
            var localRestUrl = $"http://127.0.0.1:{port}/bridge/";
            var sessionDir = Path.Combine(Path.GetTempPath(), "BridgeLiveDistribution", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(sessionDir);
            var outputDir = TestPaths.OutputDir("live-distribution", testName);

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

        private static void Banner(string message)
        {
            TestContext.Progress.WriteLine("==================================================================");
            TestContext.Progress.WriteLine(message);
            TestContext.Progress.WriteLine("==================================================================");
        }

        private static Task<UploadBlendResponse> UploadAsync(HttpClient http, string localRestUrl, string scenePath)
            => SendGetAsync<UploadBlendResponse>(http, localRestUrl, nameof(IBlenderBridgeChannel.UploadBlendAsync), scenePath);

        private static RenderOptionsData FrameOptions()
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

        private static RenderOptionsData HeavyFrameOptions()
        {
            return new RenderOptionsData
            {
                Format = RenderFormat.PNG,
                Engine = RenderEngine.Cycles,
                Samples = 128,
                ResolutionX = 512,
                ResolutionY = 512
            };
        }

        private static RenderOptionsData EeveeFrameOptions()
        {
            return new RenderOptionsData
            {
                Format = RenderFormat.PNG,
                Engine = RenderEngine.Eevee,
                Samples = 16,
                ResolutionX = 640,
                ResolutionY = 360
            };
        }

        private static RenderOptionsData GreasePencilFrameOptions()
        {
            return new RenderOptionsData
            {
                Format = RenderFormat.PNG,
                Engine = RenderEngine.GreasePencil,
                Samples = 16,
                ResolutionX = 640,
                ResolutionY = 360
            };
        }

        private static RenderOptionsData LargeCyclesFrameOptions()
        {
            return new RenderOptionsData
            {
                Format = RenderFormat.PNG,
                Engine = RenderEngine.Cycles,
                Samples = 128,
                ResolutionX = 1920,
                ResolutionY = 1080
            };
        }

        private static RenderOptionsData LargeEeveeFrameOptions()
        {
            return new RenderOptionsData
            {
                Format = RenderFormat.PNG,
                Engine = RenderEngine.Eevee,
                Samples = 64,
                ResolutionX = 1920,
                ResolutionY = 1080
            };
        }

        private static RenderOptionsData TiledOptions()
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

        private static TileOptionsData Tiles()
        {
            return new TileOptionsData { OverlapPx = 8, BlendMode = TileBlendMode.CenterPriorityCrop };
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
                    TestContext.Progress.WriteLine($"Job {jobId}: {job.Status} ({job.OverallProgress:P0}) {job.ErrorMessage}");
                    last = job.Status;
                }

                if (string.Equals(job.Status, ProcessingJobStatus.Failed.ToString(), StringComparison.OrdinalIgnoreCase))
                {
                    if (!string.IsNullOrWhiteSpace(job.ErrorMessage) && job.ErrorMessage.Contains("No fallback nodes available", StringComparison.OrdinalIgnoreCase))
                        Assert.Ignore($"Skipped — deployed capacity unavailable: {job.ErrorMessage}");
                    Assert.Fail($"Job {jobId} failed: {job.ErrorMessage}");
                }

                if (job.IsCompleted)
                    return job;

                await Task.Delay(POLL);
            }

            Assert.Fail($"Job {jobId} did not complete within {TIMEOUT}.");
            return null!;
        }

        #endregion
    }
}
