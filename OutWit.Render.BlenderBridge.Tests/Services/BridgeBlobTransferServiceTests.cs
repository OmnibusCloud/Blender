using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using OutWit.Cloud.Data.Access;
using OutWit.Cloud.SDK;
using OutWit.Cloud.SDK.Blobs;
using OutWit.Cloud.SDK.Jobs;
using OutWit.Cloud.SDK.Scripts;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;
using OutWit.Render.BlenderBridge.Services.Render;
using OutWit.Shared.Storage.Providers;

namespace OutWit.Render.BlenderBridge.Tests.Services
{
    /// <summary>
    /// The blob transfer service runs uploads as background transfers (start once, poll status) so
    /// the addon's REST calls stay fast no matter how large the scene is — the old synchronous
    /// shape held one HTTP request open for the whole cloud push and timed out on large files.
    /// These tests drive the transfer lifecycle against a gated fake blob client.
    /// </summary>
    [TestFixture]
    public class BridgeBlobTransferServiceTests
    {
        #region Fields

        private string m_tempDir = null!;
        private FakeBlobs m_blobs = null!;
        private BridgeBlobTransferService m_service = null!;

        #endregion

        #region Setup

        [SetUp]
        public void Setup()
        {
            m_tempDir = Path.Combine(Path.GetTempPath(), "bridge-upload-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(m_tempDir);

            m_blobs = new FakeBlobs();
            m_service = new BridgeBlobTransferService(new ServiceCollection().BuildServiceProvider())
            {
                CloudConnectionService = new FakeCloudConnectionService(new FakeWitCloudClient(m_blobs)),
                Logger = NullLogger<BridgeBlobTransferService>.Instance
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
        public async Task UploadRunsInBackgroundAndCompletesTest()
        {
            var filePath = CreateFile("scene.blend", 100_000);
            m_blobs.Gate = new SemaphoreSlim(0);

            var started = await m_service.StartUploadBlendAsync(filePath);
            var midway = await m_service.GetUploadStatusAsync(started.TransferId);
            m_blobs.Gate.Release();
            var completed = await WaitForStatusAsync(started.TransferId, me => me.Status != UploadStatusResponse.STATUS_IN_PROGRESS);

            Assert.Multiple(() =>
            {
                Assert.That(started.Status, Is.EqualTo(UploadStatusResponse.STATUS_IN_PROGRESS));
                Assert.That(started.TransferId, Is.Not.EqualTo(Guid.Empty));
                Assert.That(started.FileName, Is.EqualTo("scene.blend"));
                Assert.That(started.TotalBytes, Is.EqualTo(100_000));

                Assert.That(midway.Status, Is.EqualTo(UploadStatusResponse.STATUS_IN_PROGRESS));

                Assert.That(completed.Status, Is.EqualTo(UploadStatusResponse.STATUS_COMPLETED));
                Assert.That(completed.Result, Is.Not.Null);
                Assert.That(completed.Result!.Uploaded, Is.True);
                Assert.That(completed.Result.BlobId, Is.Not.EqualTo(Guid.Empty));
                Assert.That(completed.Result.FileName, Is.EqualTo("scene.blend"));
                Assert.That(completed.Result.FileSize, Is.EqualTo(100_000));
                Assert.That(completed.Result.Message, Is.EqualTo("Blend uploaded successfully."));
            });
        }

        [Test]
        public async Task StartUploadFileUsesTheFileSuccessMessageTest()
        {
            var filePath = CreateFile("cache_0001.vdb", 10_000);

            var started = await m_service.StartUploadFileAsync(filePath);
            var completed = await WaitForStatusAsync(started.TransferId, me => me.Status != UploadStatusResponse.STATUS_IN_PROGRESS);

            Assert.Multiple(() =>
            {
                Assert.That(completed.Status, Is.EqualTo(UploadStatusResponse.STATUS_COMPLETED));
                Assert.That(completed.Result!.Message, Is.EqualTo("File uploaded successfully."));
            });
        }

        [Test]
        public void StartUploadForMissingFileFailsTheStartCallTest()
        {
            Assert.Multiple(() =>
            {
                Assert.ThrowsAsync<FileNotFoundException>(
                    () => m_service.StartUploadBlendAsync(Path.Combine(m_tempDir, "missing.blend")));
                Assert.ThrowsAsync<InvalidOperationException>(
                    () => m_service.StartUploadBlendAsync("  "));
            });
        }

        #endregion

        #region Failure / Cancel Tests

        [Test]
        public async Task FailedUploadSurfacesErrorInStatusTest()
        {
            var filePath = CreateFile("scene.blend", 10_000);
            m_blobs.FailureMessage = "chunk transport broke";

            var started = await m_service.StartUploadBlendAsync(filePath);
            var failed = await WaitForStatusAsync(started.TransferId, me => me.Status != UploadStatusResponse.STATUS_IN_PROGRESS);

            Assert.Multiple(() =>
            {
                Assert.That(failed.Status, Is.EqualTo(UploadStatusResponse.STATUS_FAILED));
                Assert.That(failed.Error, Does.Contain("chunk transport broke"));
            });
        }

        [Test]
        public async Task CancelStopsTheUploadTest()
        {
            var filePath = CreateFile("scene.blend", 100_000);
            m_blobs.Gate = new SemaphoreSlim(0);

            var started = await m_service.StartUploadBlendAsync(filePath);
            var cancelled = await m_service.CancelUploadAsync(started.TransferId);
            var terminal = await WaitForStatusAsync(started.TransferId, me => me.Status != UploadStatusResponse.STATUS_IN_PROGRESS);
            var cancelAgain = await m_service.CancelUploadAsync(started.TransferId);

            Assert.Multiple(() =>
            {
                Assert.That(cancelled, Is.True);
                Assert.That(terminal.Status, Is.EqualTo(UploadStatusResponse.STATUS_CANCELLED));
                Assert.That(cancelAgain, Is.False, "cancel on a terminal transfer reports false");
            });
        }

        [Test]
        public async Task GetStatusForUnknownTransferReturnsNotFoundTest()
        {
            var status = await m_service.GetUploadStatusAsync(Guid.NewGuid());

            Assert.Multiple(() =>
            {
                Assert.That(status.Status, Is.EqualTo(UploadStatusResponse.STATUS_NOT_FOUND));
                Assert.That(status.Error, Is.Not.Null.And.Not.Empty);
            });
        }

        #endregion

        #region Synchronous Wrapper Tests

        [Test]
        public async Task UploadBlendAwaitsTheTransferAndReturnsTheResponseTest()
        {
            var filePath = CreateFile("scene.blend", 10_000);

            var response = await m_service.UploadBlendAsync(filePath);

            Assert.Multiple(() =>
            {
                Assert.That(response.Uploaded, Is.True);
                Assert.That(response.FileName, Is.EqualTo("scene.blend"));
                Assert.That(response.FileSize, Is.EqualTo(10_000));
            });
        }

        [Test]
        public void UploadBlendThrowsWhenTheTransferFailsTest()
        {
            var filePath = CreateFile("scene.blend", 10_000);
            m_blobs.FailureMessage = "not connected";

            Assert.ThrowsAsync<InvalidOperationException>(() => m_service.UploadBlendAsync(filePath));
        }

        #endregion

        #region Tools

        private string CreateFile(string fileName, int size)
        {
            var path = Path.Combine(m_tempDir, fileName);
            var content = new byte[size];
            new Random(42).NextBytes(content);
            File.WriteAllBytes(path, content);
            return path;
        }

        private async Task<UploadStatusResponse> WaitForStatusAsync(
            Guid transferId,
            Func<UploadStatusResponse, bool> predicate,
            int timeoutMs = 10_000)
        {
            var deadline = DateTime.UtcNow.AddMilliseconds(timeoutMs);
            while (true)
            {
                var status = await m_service.GetUploadStatusAsync(transferId);
                if (predicate(status))
                    return status;

                if (DateTime.UtcNow > deadline)
                    Assert.Fail($"Timed out waiting for upload status condition; last status: {status.Status}, error: {status.Error}");

                await Task.Delay(20);
            }
        }

        #endregion

        #region Fakes

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
        /// Fake blob store whose file upload (optionally) waits on <see cref="Gate"/> before
        /// returning — deterministic in-progress snapshots for the tests.
        /// </summary>
        private sealed class FakeBlobs : IWitCloudBlobs
        {
            public SemaphoreSlim? Gate { get; set; }

            public string? FailureMessage { get; set; }

            public async Task<Guid> UploadBlobFromFileAsync(string filePath, int chunkSize = IWitCloudBlobs.DEFAULT_CHUNK_SIZE, CancellationToken ct = default)
            {
                if (FailureMessage != null)
                    throw new InvalidOperationException(FailureMessage);

                if (Gate != null)
                    await Gate.WaitAsync(ct);
                ct.ThrowIfCancellationRequested();

                return Guid.NewGuid();
            }

            public Task<Guid> UploadBlobAsync(byte[] data, string fileName, int chunkSize = IWitCloudBlobs.DEFAULT_CHUNK_SIZE, CancellationToken ct = default) => throw new NotSupportedException();

            public Task<byte[]> DownloadBlobAsync(Guid blobId, CancellationToken ct = default) => throw new NotSupportedException();

            public Task DownloadBlobToFileAsync(Guid blobId, string localPath, int chunkSize = IWitCloudBlobs.DEFAULT_CHUNK_SIZE, CancellationToken ct = default) => throw new NotSupportedException();

            public Task<BlobInfo> GetBlobInfoAsync(Guid blobId, CancellationToken ct = default) => throw new NotSupportedException();

            public Task DeleteBlobAsync(Guid blobId, CancellationToken ct = default) => throw new NotSupportedException();
        }

        #endregion
    }
}
