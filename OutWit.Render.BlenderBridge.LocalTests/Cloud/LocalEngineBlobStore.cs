using OutWit.Engine.Interfaces;
using OutWit.Shared.Storage.Providers;

namespace OutWit.Render.BlenderBridge.LocalTests.Cloud
{
    /// <summary>
    /// In-memory + on-disk blob store shared between the in-process engine (as
    /// <see cref="IWitBlobService"/> — how render activities read scene inputs and write result
    /// blobs) and the bridge's SDK blob surface (<see cref="LocalEngineBlobs"/>). One instance backs
    /// both, so a blob the bridge uploads is the exact file the engine renders, and a blob the engine
    /// produces is the exact file the bridge downloads — no wire, no server.
    /// </summary>
    internal sealed class LocalEngineBlobStore : IWitBlobService
    {
        #region Fields

        private readonly object m_lock = new();
        private readonly Dictionary<Guid, Entry> m_blobs = new();
        private readonly string m_storagePath;

        #endregion

        #region Constructors

        public LocalEngineBlobStore(string storagePath)
        {
            m_storagePath = storagePath;
            Directory.CreateDirectory(m_storagePath);
        }

        #endregion

        #region IWitBlobService

        public Task<string> GetLocalPathAsync(Guid blobId)
        {
            lock (m_lock)
            {
                if (!m_blobs.TryGetValue(blobId, out var entry))
                    throw new FileNotFoundException($"Blob '{blobId}' is not registered in the local engine blob store.");

                return Task.FromResult(entry.Path);
            }
        }

        public Task<Guid> UploadFileAsync(string localFilePath)
        {
            var blobId = Guid.NewGuid();
            var fileName = Path.GetFileName(localFilePath);
            var destinationPath = Path.Combine(m_storagePath, $"{blobId:N}{Path.GetExtension(localFilePath)}");
            File.Copy(localFilePath, destinationPath, overwrite: true);
            Record(blobId, destinationPath, fileName);
            return Task.FromResult(blobId);
        }

        public Task<Guid> UploadBytesAsync(byte[] data, string fileName)
        {
            var blobId = Guid.NewGuid();
            var destinationPath = Path.Combine(m_storagePath, $"{blobId:N}{Path.GetExtension(fileName)}");
            File.WriteAllBytes(destinationPath, data);
            Record(blobId, destinationPath, fileName);
            return Task.FromResult(blobId);
        }

        #endregion

        #region Blob surface (used by LocalEngineBlobs)

        public byte[] ReadBytes(Guid blobId)
        {
            lock (m_lock)
            {
                if (!m_blobs.TryGetValue(blobId, out var entry))
                    throw new FileNotFoundException($"Blob '{blobId}' is not registered in the local engine blob store.");

                return File.ReadAllBytes(entry.Path);
            }
        }

        public BlobInfo GetInfo(Guid blobId)
        {
            lock (m_lock)
            {
                if (!m_blobs.TryGetValue(blobId, out var entry))
                    throw new FileNotFoundException($"Blob '{blobId}' is not registered in the local engine blob store.");

                var size = File.Exists(entry.Path) ? new FileInfo(entry.Path).Length : 0;
                return new BlobInfo
                {
                    Id = blobId,
                    FileName = entry.FileName,
                    Size = size,
                    CreatedAtUtc = entry.CreatedAtUtc
                };
            }
        }

        public string GetPath(Guid blobId)
        {
            lock (m_lock)
            {
                if (!m_blobs.TryGetValue(blobId, out var entry))
                    throw new FileNotFoundException($"Blob '{blobId}' is not registered in the local engine blob store.");

                return entry.Path;
            }
        }

        public void Delete(Guid blobId)
        {
            lock (m_lock)
            {
                if (m_blobs.Remove(blobId, out var entry) && File.Exists(entry.Path))
                {
                    try { File.Delete(entry.Path); }
                    catch { /* best-effort */ }
                }
            }
        }

        #endregion

        #region Tools

        private void Record(Guid blobId, string path, string fileName)
        {
            lock (m_lock)
                m_blobs[blobId] = new Entry(path, fileName, GetUtcNow());
        }

        // new DateTime() argless is unavailable inside workflow scripts but fine here; tests stamp
        // their own timestamps. Using a fixed epoch keeps BlobInfo deterministic for assertions.
        private static DateTime GetUtcNow() => DateTime.UtcNow;

        #endregion

        #region Nested Types

        private readonly record struct Entry(string Path, string FileName, DateTime CreatedAtUtc);

        #endregion
    }
}
