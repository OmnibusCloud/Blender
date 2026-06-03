using System.Collections.Concurrent;
using OutWit.Cloud.Data.Processing;
using OutWit.Engine.Interfaces;

namespace OutWit.Render.BlenderBridge.LocalTests.Cloud
{
    /// <summary>
    /// Shared state for the in-process engine-backed cloud client: the singleton engine, the blob
    /// store both the engine and the SDK blob surface use, the staged <c>@Scripts</c> directory
    /// (scriptName → <c>{scriptName}.wit</c> is an identity map), the in-flight job registry, and a
    /// lock that serialises engine runs (the engine is a process-wide singleton).
    /// </summary>
    internal sealed class LocalEngineRuntime
    {
        #region Constructors

        public LocalEngineRuntime(IWitEngine engine, LocalEngineBlobStore blobStore, string scriptsDirectory)
        {
            Engine = engine;
            BlobStore = blobStore;
            ScriptsDirectory = scriptsDirectory;
        }

        #endregion

        #region Properties

        public IWitEngine Engine { get; }

        public LocalEngineBlobStore BlobStore { get; }

        public string ScriptsDirectory { get; }

        public ConcurrentDictionary<Guid, LocalEngineJobState> Jobs { get; } = new();

        public SemaphoreSlim EngineLock { get; } = new(1, 1);

        #endregion
    }

    /// <summary>
    /// Mutable per-job state. The background run task updates <see cref="Status"/> /
    /// <see cref="Job"/>; the SDK Jobs surface reads them when polled.
    /// </summary>
    internal sealed class LocalEngineJobState
    {
        public required Guid JobId { get; init; }

        public required string ScriptName { get; init; }

        public ProcessingJobStatus Status { get; set; } = ProcessingJobStatus.Pending;

        public IWitJob? Job { get; set; }

        public string? Error { get; set; }

        public double Progress { get; set; }
    }
}
