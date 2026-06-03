namespace OutWit.Render.BlenderBridge.Services.Hosting.Interfaces
{
    /// <summary>
    /// Tracks bridge-launched jobs so bridge lifetime watchdog logic can decide whether active work still exists.
    /// </summary>
    public interface IBridgeJobTrackerService
    {
        /// <summary>
        /// Records one launched job for later lifecycle checks.
        /// </summary>
        void TrackJob(Guid jobId);

        /// <summary>
        /// Returns whether any tracked jobs may still be active after pruning completed jobs.
        /// </summary>
        Task<bool> HasTrackedActiveJobsAsync(CancellationToken cancellationToken = default);
    }
}
