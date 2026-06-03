using OutWit.Cloud.Data.Processing;
using OutWit.Cloud.SDK;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;
using OutWit.Render.BlenderBridge.Services.Hosting.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Hosting
{
    /// <summary>
    /// Tracks bridge-launched jobs for lifecycle decisions.
    /// </summary>
    [InjectableHost]
    public partial class BridgeJobTrackerService : IBridgeJobTrackerService
    {
        #region Fields

        private readonly object m_sync = new();
        private readonly HashSet<Guid> m_trackedJobs = [];

        #endregion

        #region IBridgeJobTrackerService

        public void TrackJob(Guid jobId)
        {
            if (jobId == Guid.Empty)
                return;

            lock (m_sync)
            {
                m_trackedJobs.Add(jobId);
            }
        }

        public async Task<bool> HasTrackedActiveJobsAsync(CancellationToken cancellationToken = default)
        {
            List<Guid> snapshot;
            lock (m_sync)
            {
                snapshot = [.. m_trackedJobs];
            }

            if (snapshot.Count == 0)
                return false;

            var client = await CloudConnectionService.GetClientAsync(cancellationToken);
            if (client == null)
                return snapshot.Count > 0;

            var completed = new List<Guid>();
            foreach (var jobId in snapshot)
            {
                ProcessingJobInfo info;
                try
                {
                    info = await client.Jobs.GetStatusAsync(jobId, cancellationToken);
                }
                catch
                {
                    continue;
                }

                if (info.Status is ProcessingJobStatus.Completed or ProcessingJobStatus.Failed or ProcessingJobStatus.Cancelled)
                    completed.Add(jobId);
            }

            if (completed.Count > 0)
            {
                lock (m_sync)
                {
                    foreach (var jobId in completed)
                        m_trackedJobs.Remove(jobId);
                }
            }

            lock (m_sync)
            {
                return m_trackedJobs.Count > 0;
            }
        }

        #endregion

        #region Properties

        [Inject]
        public IBridgeCloudConnectionService CloudConnectionService { get; set; } = null!;

        #endregion
    }
}
