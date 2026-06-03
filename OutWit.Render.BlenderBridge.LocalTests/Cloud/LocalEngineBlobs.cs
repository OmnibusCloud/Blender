using OutWit.Cloud.SDK.Blobs;
using OutWit.Shared.Storage.Providers;

namespace OutWit.Render.BlenderBridge.LocalTests.Cloud
{
    /// <summary>
    /// <see cref="IWitCloudBlobs"/> over the shared <see cref="LocalEngineBlobStore"/>. The bridge
    /// uploads the scene here and the engine reads it from the same store; result blobs the engine
    /// writes are downloaded back through here. No chunking / no wire — it is one in-process store.
    /// </summary>
    internal sealed class LocalEngineBlobs : IWitCloudBlobs
    {
        #region Fields

        private readonly LocalEngineBlobStore m_store;

        #endregion

        #region Constructors

        public LocalEngineBlobs(LocalEngineBlobStore store)
        {
            m_store = store;
        }

        #endregion

        #region IWitCloudBlobs

        public Task<Guid> UploadBlobAsync(byte[] data, string fileName, int chunkSize = IWitCloudBlobs.DEFAULT_CHUNK_SIZE, CancellationToken ct = default)
        {
            return m_store.UploadBytesAsync(data, fileName);
        }

        public Task<Guid> UploadBlobFromFileAsync(string filePath, int chunkSize = IWitCloudBlobs.DEFAULT_CHUNK_SIZE, CancellationToken ct = default)
        {
            return m_store.UploadFileAsync(filePath);
        }

        public Task<byte[]> DownloadBlobAsync(Guid blobId, CancellationToken ct = default)
        {
            return Task.FromResult(m_store.ReadBytes(blobId));
        }

        public Task DownloadBlobToFileAsync(Guid blobId, string localPath, int chunkSize = IWitCloudBlobs.DEFAULT_CHUNK_SIZE, CancellationToken ct = default)
        {
            var directory = Path.GetDirectoryName(localPath);
            if (!string.IsNullOrEmpty(directory))
                Directory.CreateDirectory(directory);

            File.Copy(m_store.GetPath(blobId), localPath, overwrite: true);
            return Task.CompletedTask;
        }

        public Task<BlobInfo> GetBlobInfoAsync(Guid blobId, CancellationToken ct = default)
        {
            return Task.FromResult(m_store.GetInfo(blobId));
        }

        public Task DeleteBlobAsync(Guid blobId, CancellationToken ct = default)
        {
            m_store.Delete(blobId);
            return Task.CompletedTask;
        }

        #endregion
    }
}
