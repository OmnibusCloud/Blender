using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using OutWit.Cloud.Data.Access;
using OutWit.Cloud.SDK;
using OutWit.Cloud.SDK.Blobs;
using OutWit.Cloud.SDK.Jobs;
using OutWit.Cloud.SDK.Scripts;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;
using OutWit.Render.BlenderBridge.Services.Render;
using OutWit.Render.BlenderBridge.Services.Render.Interfaces;
using OutWit.Shared.Storage.Providers;

namespace OutWit.Render.BlenderBridge.Tests.Services
{
    /// <summary>
    /// The download service runs result pulls as background transfers (start once, poll status) so
    /// the addon's REST calls stay fast no matter how large the result is — the old synchronous
    /// shape held one HTTP request open for the whole download and timed out on large videos.
    /// These tests drive the transfer lifecycle against a gated fake blob client.
    /// </summary>
    [TestFixture]
    public class BridgeDownloadServiceTests
    {
        #region Fields

        private string m_tempDir = null!;
        private FakeBlobs m_blobs = null!;
        private FakeJobQueryService m_jobs = null!;
        private BridgeDownloadService m_service = null!;

        #endregion

        #region Setup

        [SetUp]
        public void Setup()
        {
            m_tempDir = Path.Combine(Path.GetTempPath(), "bridge-download-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(m_tempDir);

            m_blobs = new FakeBlobs();
            m_jobs = new FakeJobQueryService();
            m_service = new BridgeDownloadService(new ServiceCollection().BuildServiceProvider())
            {
                Settings = new BridgeSettings { DownloadCachePath = m_tempDir },
                CloudConnectionService = new FakeCloudConnectionService(new FakeWitCloudClient(m_blobs)),
                JobQueryService = m_jobs,
                Logger = NullLogger<BridgeDownloadService>.Instance
            };
        }

        [TearDown]
        public void TearDown()
        {
            m_blobs.Gate?.Release(100);
            if (Directory.Exists(m_tempDir))
                Directory.Delete(m_tempDir, recursive: true);
        }

        #endregion

        #region Start / Poll Tests

        [Test]
        public async Task DownloadRunsInBackgroundReportsProgressAndCompletesTest()
        {
            var jobId = Guid.NewGuid();
            var blobId = Guid.NewGuid();
            var content = CreateContent(200_000);
            m_blobs.Add(blobId, "result.mp4", content);
            m_blobs.Gate = new SemaphoreSlim(0);
            m_jobs.SetJob(jobId, blobId);

            var started = await m_service.StartDownloadResultAsync(jobId);
            Assert.That(started.Status, Is.EqualTo(DownloadStatusResponse.STATUS_IN_PROGRESS));

            var midway = await WaitForStatusAsync(jobId, me => me.DownloadedBytes > 0);
            m_blobs.Gate.Release();
            var completed = await WaitForStatusAsync(jobId, me => me.Status != DownloadStatusResponse.STATUS_IN_PROGRESS);

            var expectedPath = Path.Combine(m_tempDir, $"{jobId:N}_{blobId:N}_result.mp4");
            Assert.Multiple(() =>
            {
                Assert.That(midway.Status, Is.EqualTo(DownloadStatusResponse.STATUS_IN_PROGRESS));
                Assert.That(midway.TotalBytes, Is.EqualTo(content.Length));
                Assert.That(midway.DownloadedBytes, Is.LessThan(content.Length), "midway snapshot must not read complete");
                Assert.That(midway.CurrentFileName, Is.EqualTo("result.mp4"));

                Assert.That(completed.Status, Is.EqualTo(DownloadStatusResponse.STATUS_COMPLETED));
                Assert.That(completed.Progress, Is.EqualTo(1.0));
                Assert.That(completed.ItemsCompleted, Is.EqualTo(1));
                Assert.That(completed.Result, Is.Not.Null);
                Assert.That(completed.Result!.Downloaded, Is.True);
                Assert.That(completed.Result.LocalPath, Is.EqualTo(expectedPath));
                Assert.That(File.Exists(expectedPath), Is.True);
                Assert.That(File.Exists(expectedPath + ".partial"), Is.False, "the partial file must be promoted");
                Assert.That(File.ReadAllBytes(expectedPath), Is.EqualTo(content));
            });
        }

        [Test]
        public async Task StartWhileInProgressJoinsTheActiveTransferTest()
        {
            var jobId = Guid.NewGuid();
            var blobId = Guid.NewGuid();
            m_blobs.Add(blobId, "result.mp4", CreateContent(50_000));
            m_blobs.Gate = new SemaphoreSlim(0);
            m_jobs.SetJob(jobId, blobId);

            await m_service.StartDownloadResultAsync(jobId);
            await m_service.StartDownloadResultAsync(jobId);
            m_blobs.Gate.Release();
            await WaitForStatusAsync(jobId, me => me.Status == DownloadStatusResponse.STATUS_COMPLETED);

            Assert.That(m_blobs.DownloadToFileCalls, Is.EqualTo(1), "a second start must join, not restart");
        }

        [Test]
        public async Task CompletedDownloadIsServedFromDiskWithoutRedownloadTest()
        {
            var jobId = Guid.NewGuid();
            var blobId = Guid.NewGuid();
            m_blobs.Add(blobId, "result.mp4", CreateContent(50_000));
            m_jobs.SetJob(jobId, blobId);

            await m_service.StartDownloadResultAsync(jobId);
            await WaitForStatusAsync(jobId, me => me.Status == DownloadStatusResponse.STATUS_COMPLETED);

            var again = await m_service.StartDownloadResultAsync(jobId);

            Assert.Multiple(() =>
            {
                Assert.That(again.Status, Is.EqualTo(DownloadStatusResponse.STATUS_COMPLETED));
                Assert.That(again.Result, Is.Not.Null);
                Assert.That(m_blobs.DownloadToFileCalls, Is.EqualTo(1));
            });
        }

        [Test]
        public async Task MultiItemDownloadAggregatesTotalsTest()
        {
            var jobId = Guid.NewGuid();
            var blobA = Guid.NewGuid();
            var blobB = Guid.NewGuid();
            m_blobs.Add(blobA, "frame_0001.png", CreateContent(30_000));
            m_blobs.Add(blobB, "frame_0002.png", CreateContent(70_000));
            m_jobs.SetJob(jobId, blobA, blobB);

            await m_service.StartDownloadResultAsync(jobId);
            var completed = await WaitForStatusAsync(jobId, me => me.Status == DownloadStatusResponse.STATUS_COMPLETED);

            Assert.Multiple(() =>
            {
                Assert.That(completed.ItemCount, Is.EqualTo(2));
                Assert.That(completed.ItemsCompleted, Is.EqualTo(2));
                Assert.That(completed.TotalBytes, Is.EqualTo(100_000));
                Assert.That(completed.DownloadedBytes, Is.EqualTo(100_000));
                Assert.That(completed.Result!.Items, Has.Count.EqualTo(2));
                Assert.That(completed.Result.FileName, Is.EqualTo("frame_0001.png"), "primary item is the first blob");
            });
        }

        #endregion

        #region Failure / Cancel Tests

        [Test]
        public async Task FailedDownloadSurfacesErrorCleansPartialAndCanRestartTest()
        {
            var jobId = Guid.NewGuid();
            var blobId = Guid.NewGuid();
            m_blobs.Add(blobId, "result.mp4", CreateContent(50_000));
            m_blobs.FailureMessage = "chunk transport broke";
            m_jobs.SetJob(jobId, blobId);

            await m_service.StartDownloadResultAsync(jobId);
            var failed = await WaitForStatusAsync(jobId, me => me.Status != DownloadStatusResponse.STATUS_IN_PROGRESS);

            m_blobs.FailureMessage = null;
            await m_service.StartDownloadResultAsync(jobId);
            var completed = await WaitForStatusAsync(jobId, me => me.Status != DownloadStatusResponse.STATUS_IN_PROGRESS);

            Assert.Multiple(() =>
            {
                Assert.That(failed.Status, Is.EqualTo(DownloadStatusResponse.STATUS_FAILED));
                Assert.That(failed.Error, Does.Contain("chunk transport broke"));
                Assert.That(Directory.GetFiles(m_tempDir, "*.partial"), Is.Empty, "failed transfers must not leave partials");
                Assert.That(completed.Status, Is.EqualTo(DownloadStatusResponse.STATUS_COMPLETED), "a failed transfer must restart on the next start");
                Assert.That(m_blobs.DownloadToFileCalls, Is.EqualTo(2));
            });
        }

        [Test]
        public async Task CancelStopsTheTransferAndCleansPartialTest()
        {
            var jobId = Guid.NewGuid();
            var blobId = Guid.NewGuid();
            m_blobs.Add(blobId, "result.mp4", CreateContent(200_000));
            m_blobs.Gate = new SemaphoreSlim(0);
            m_jobs.SetJob(jobId, blobId);

            await m_service.StartDownloadResultAsync(jobId);
            await WaitForStatusAsync(jobId, me => me.DownloadedBytes > 0);

            var cancelled = await m_service.CancelDownloadResultAsync(jobId);
            var terminal = await WaitForStatusAsync(jobId, me => me.Status != DownloadStatusResponse.STATUS_IN_PROGRESS);
            var cancelAgain = await m_service.CancelDownloadResultAsync(jobId);

            Assert.Multiple(() =>
            {
                Assert.That(cancelled, Is.True);
                Assert.That(terminal.Status, Is.EqualTo(DownloadStatusResponse.STATUS_CANCELLED));
                Assert.That(Directory.GetFiles(m_tempDir, "*.partial"), Is.Empty, "cancelled transfers must not leave partials");
                Assert.That(cancelAgain, Is.False, "cancel on a terminal transfer reports false");
            });
        }

        [Test]
        public async Task GetStatusForUnknownJobReturnsNotFoundTest()
        {
            var status = await m_service.GetDownloadResultStatusAsync(Guid.NewGuid());

            Assert.Multiple(() =>
            {
                Assert.That(status.Status, Is.EqualTo(DownloadStatusResponse.STATUS_NOT_FOUND));
                Assert.That(status.Error, Is.Not.Null.And.Not.Empty);
            });
        }

        #endregion

        #region Synchronous Wrapper Tests

        [Test]
        public async Task DownloadResultAwaitsTheTransferAndReturnsTheResultTest()
        {
            var jobId = Guid.NewGuid();
            var blobId = Guid.NewGuid();
            var content = CreateContent(50_000);
            m_blobs.Add(blobId, "result.mp4", content);
            m_jobs.SetJob(jobId, blobId);

            var response = await m_service.DownloadResultAsync(jobId);

            Assert.Multiple(() =>
            {
                Assert.That(response.Downloaded, Is.True);
                Assert.That(response.FileSize, Is.EqualTo(content.Length));
                Assert.That(File.Exists(response.LocalPath), Is.True);
            });
        }

        [Test]
        public void DownloadResultThrowsWhenJobHasNoResultBlobTest()
        {
            var jobId = Guid.NewGuid();
            m_jobs.SetJob(jobId);

            Assert.ThrowsAsync<InvalidOperationException>(() => m_service.DownloadResultAsync(jobId));
        }

        #endregion

        #region Tools

        private static byte[] CreateContent(int size)
        {
            var content = new byte[size];
            new Random(42).NextBytes(content);
            return content;
        }

        private async Task<DownloadStatusResponse> WaitForStatusAsync(
            Guid jobId,
            Func<DownloadStatusResponse, bool> predicate,
            int timeoutMs = 10_000)
        {
            var deadline = DateTime.UtcNow.AddMilliseconds(timeoutMs);
            while (true)
            {
                var status = await m_service.GetDownloadResultStatusAsync(jobId);
                if (predicate(status))
                    return status;

                if (DateTime.UtcNow > deadline)
                    Assert.Fail($"Timed out waiting for download status condition; last status: {status.Status}, {status.DownloadedBytes}/{status.TotalBytes} bytes, error: {status.Error}");

                await Task.Delay(20);
            }
        }

        #endregion

        #region Fakes

        private sealed class FakeJobQueryService : IBridgeJobQueryService
        {
            private GetJobResponse m_job = null!;

            public void SetJob(Guid jobId, params Guid[] resultBlobIds)
            {
                m_job = new GetJobResponse
                {
                    JobId = jobId,
                    Status = "Completed",
                    IsCompleted = true,
                    ResultBlobIds = resultBlobIds.Select(me => (Guid?)me).ToList()
                };
            }

            public Task<GetJobResponse> GetJobAsync(Guid jobId, CancellationToken cancellationToken = default)
            {
                return Task.FromResult(m_job);
            }

            public Task<bool> CancelJobAsync(Guid jobId, CancellationToken cancellationToken = default)
            {
                return Task.FromResult(true);
            }
        }

        private sealed class FakeCloudConnectionService : IBridgeCloudConnectionService
        {
            private readonly IWitCloudClient m_client;

            public FakeCloudConnectionService(IWitCloudClient client)
            {
                m_client = client;
            }

            public Task<bool> EnsureConnectedAsync(CancellationToken cancellationToken = default) => Task.FromResult(true);

            public Task<bool> IsConnectedAsync(CancellationToken cancellationToken = default) => Task.FromResult(true);

            public Task<IWitCloudClient?> GetClientAsync(CancellationToken cancellationToken = default) => Task.FromResult<IWitCloudClient?>(m_client);
        }

        private sealed class FakeWitCloudClient : IWitCloudClient
        {
            public FakeWitCloudClient(IWitCloudBlobs blobs)
            {
                Blobs = blobs;
            }

            public Task ConnectAsync(CancellationToken ct = default) => Task.CompletedTask;

            public Task<ExecutionScopeOptions> GetExecutionScopeOptionsAsync(CancellationToken ct = default) => throw new NotSupportedException();

            public IWitCloudScripts Scripts => throw new NotSupportedException();

            public IWitCloudJobs Jobs => throw new NotSupportedException();

            public IWitCloudBlobs Blobs { get; }

            public ValueTask DisposeAsync() => ValueTask.CompletedTask;
        }

        /// <summary>
        /// In-memory blob store whose file download writes the first half, then (optionally) waits on
        /// <see cref="Gate"/> before writing the rest — deterministic midway snapshots for the tests.
        /// </summary>
        private sealed class FakeBlobs : IWitCloudBlobs
        {
            private readonly Dictionary<Guid, (string FileName, byte[] Content)> m_blobs = new();

            private int m_downloadToFileCalls;

            public SemaphoreSlim? Gate { get; set; }

            public string? FailureMessage { get; set; }

            public int DownloadToFileCalls => m_downloadToFileCalls;

            public void Add(Guid blobId, string fileName, byte[] content)
            {
                m_blobs[blobId] = (fileName, content);
            }

            public Task<BlobInfo> GetBlobInfoAsync(Guid blobId, CancellationToken ct = default)
            {
                var (fileName, content) = m_blobs[blobId];
                return Task.FromResult(new BlobInfo
                {
                    Id = blobId,
                    FileName = fileName,
                    Size = content.Length,
                    CreatedAtUtc = DateTime.UtcNow
                });
            }

            public async Task DownloadBlobToFileAsync(Guid blobId, string localPath, int chunkSize = IWitCloudBlobs.DEFAULT_CHUNK_SIZE, CancellationToken ct = default)
            {
                Interlocked.Increment(ref m_downloadToFileCalls);

                if (FailureMessage != null)
                    throw new InvalidOperationException(FailureMessage);

                var content = m_blobs[blobId].Content;
                var half = content.Length / 2;

                await File.WriteAllBytesAsync(localPath, content[..half], ct);

                if (Gate != null)
                    await Gate.WaitAsync(ct);
                ct.ThrowIfCancellationRequested();

                await using var stream = new FileStream(localPath, FileMode.Append, FileAccess.Write);
                await stream.WriteAsync(content.AsMemory(half), ct);
            }

            public Task<Guid> UploadBlobAsync(byte[] data, string fileName, int chunkSize = IWitCloudBlobs.DEFAULT_CHUNK_SIZE, CancellationToken ct = default) => throw new NotSupportedException();

            public Task<Guid> UploadBlobFromFileAsync(string filePath, int chunkSize = IWitCloudBlobs.DEFAULT_CHUNK_SIZE, CancellationToken ct = default) => throw new NotSupportedException();

            public Task<byte[]> DownloadBlobAsync(Guid blobId, CancellationToken ct = default) => throw new NotSupportedException();

            public Task DeleteBlobAsync(Guid blobId, CancellationToken ct = default) => throw new NotSupportedException();
        }

        #endregion
    }
}
