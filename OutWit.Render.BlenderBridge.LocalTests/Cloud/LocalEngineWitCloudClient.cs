using OutWit.Cloud.Data.Access;
using OutWit.Cloud.SDK;
using OutWit.Cloud.SDK.Blobs;
using OutWit.Cloud.SDK.Jobs;
using OutWit.Cloud.SDK.Scripts;

namespace OutWit.Render.BlenderBridge.LocalTests.Cloud
{
    /// <summary>
    /// An <see cref="IWitCloudClient"/> whose Scripts/Jobs/Blobs are served by the public in-process
    /// <c>OutWit.Engine.Sdk</c> running the real render controller — the "public mock-runner". The
    /// bridge talks to this exactly as it talks to a live WitCloud server (same SDK interface), so a
    /// Tier-B test exercises the genuine initiator→controller contract with no server, no online
    /// clients, and no deploy cycle.
    /// </summary>
    internal sealed class LocalEngineWitCloudClient : IWitCloudClient
    {
        #region Constructors

        public LocalEngineWitCloudClient(LocalEngineRuntime runtime)
        {
            var jobs = new LocalEngineJobs(runtime);
            Jobs = jobs;
            Scripts = new LocalEngineScripts(runtime, jobs);
            Blobs = new LocalEngineBlobs(runtime.BlobStore);
        }

        #endregion

        #region IWitCloudClient

        public Task ConnectAsync(CancellationToken ct = default) => Task.CompletedTask;

        public Task<ExecutionScopeOptions> GetExecutionScopeOptionsAsync(CancellationToken ct = default)
        {
            // The local engine has no group/project topology; the bridge only reads counts + the
            // all-clients flag for its execution-scope response.
            return Task.FromResult(new ExecutionScopeOptions
            {
                CanRunOnAllClients = true,
                Groups = [],
                Projects = []
            });
        }

        public IWitCloudScripts Scripts { get; }

        public IWitCloudJobs Jobs { get; }

        public IWitCloudBlobs Blobs { get; }

        public ValueTask DisposeAsync() => ValueTask.CompletedTask;

        #endregion
    }
}
