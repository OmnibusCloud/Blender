using OutWit.Render.BlenderBridge.Contracts;

namespace OutWit.Render.BlenderBridge.Services.Render.Interfaces
{
    /// <summary>
    /// Owns bridge-side cloud job status queries.
    /// </summary>
    public interface IBridgeJobQueryService
    {
        /// <summary>
        /// Returns the current summary of one bridge-launched cloud job.
        /// </summary>
        Task<GetJobResponse> GetJobAsync(Guid jobId, CancellationToken cancellationToken = default);

        /// <summary>
        /// Requests cancellation of one bridge-launched cloud job. Returns true on success.
        /// </summary>
        Task<bool> CancelJobAsync(Guid jobId, CancellationToken cancellationToken = default);
    }
}
