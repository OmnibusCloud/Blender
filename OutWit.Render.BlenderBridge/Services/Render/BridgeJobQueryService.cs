using OutWit.Cloud.Data.Processing;
using OutWit.Cloud.SDK;
using OutWit.Cloud.SDK.Jobs;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;
using OutWit.Render.BlenderBridge.Services.Render.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Render
{
    /// <summary>
    /// Bridge-side cloud job query operations.
    /// </summary>
    [InjectableHost]
    public partial class BridgeJobQueryService : IBridgeJobQueryService
    {
        #region IBridgeJobQueryService

        public async Task<GetJobResponse> GetJobAsync(Guid jobId, CancellationToken cancellationToken = default)
        {
            if (jobId == Guid.Empty)
                throw new InvalidOperationException("Job id is required.");

            var client = await CloudConnectionService.GetClientAsync(cancellationToken)
                         ?? throw new InvalidOperationException("Bridge is not connected to the cloud.");

            var info = await client.Jobs.GetStatusAsync(jobId, cancellationToken);

            Guid? resultBlobId = null;
            List<Guid?> resultBlobIds = [];
            if (info.Status == ProcessingJobStatus.Completed)
            {
                resultBlobIds = await GetResultBlobIdsAsync(client.Jobs, jobId, cancellationToken);
                if (resultBlobIds.Count == 1)
                    resultBlobId = resultBlobIds[0];
            }

            var hasMaterializedResult = resultBlobId.HasValue || resultBlobIds.Count > 0;
            var effectiveStatus = info.Status.ToString();
            var effectiveProgress = info.OverallProgress;
            var isCompleted = info.Status == ProcessingJobStatus.Completed;

            if (info.Status == ProcessingJobStatus.Completed && !hasMaterializedResult && string.IsNullOrWhiteSpace(info.ErrorMessage))
            {
                effectiveStatus = "Finalizing";
                effectiveProgress = Math.Min(Math.Max(effectiveProgress, 0.99), 0.99);
                isCompleted = false;
            }
            else if (info.Status is ProcessingJobStatus.Pending or ProcessingJobStatus.Distributing or ProcessingJobStatus.Processing)
            {
                effectiveProgress = Math.Min(Math.Max(effectiveProgress, 0.0), 0.99);
            }

            return new GetJobResponse
            {
                JobId = info.Id,
                ScriptName = info.ScriptName,
                Status = effectiveStatus,
                OverallProgress = effectiveProgress,
                // Distributed "computation" progress is a separate axis (the Grid.ForEach work the engine
                // sees as one opaque stage); passed through raw — the effectiveProgress capping above is a
                // display nicety for the coarse OverallProgress bar only.
                DistributedProgress = info.DistributedProgress,
                IsCompleted = isCompleted,
                ResultBlobId = resultBlobId,
                ResultBlobIds = resultBlobIds,
                ErrorMessage = info.ErrorMessage
            };
        }

        public async Task<bool> CancelJobAsync(Guid jobId, CancellationToken cancellationToken = default)
        {
            if (jobId == Guid.Empty)
                throw new InvalidOperationException("Job id is required.");

            var client = await CloudConnectionService.GetClientAsync(cancellationToken)
                         ?? throw new InvalidOperationException("Bridge is not connected to the cloud.");

            await client.Jobs.CancelAsync(jobId, cancellationToken);
            return true;
        }

        private static async Task<List<Guid?>> GetResultBlobIdsAsync(IWitCloudJobs jobs, Guid jobId, CancellationToken cancellationToken)
        {
            var scalar = await TryResultAsync<Guid>(jobs, jobId, cancellationToken);
            if (scalar != Guid.Empty)
                return [scalar];

            var nullableScalar = await TryResultAsync<Guid?>(jobs, jobId, cancellationToken);
            if (nullableScalar is { } value && value != Guid.Empty)
                return [value];

            var nullableArray = ExtractBlobIds(await TryResultAsync<Guid?[]>(jobs, jobId, cancellationToken));
            if (nullableArray.Count > 0)
                return nullableArray;

            var nonNullableArray = ExtractBlobIds(await TryResultAsync<Guid[]>(jobs, jobId, cancellationToken));
            if (nonNullableArray.Count > 0)
                return nonNullableArray;

            var readOnlyNullable = ExtractBlobIds(await TryResultAsync<IReadOnlyList<Guid?>>(jobs, jobId, cancellationToken));
            if (readOnlyNullable.Count > 0)
                return readOnlyNullable;

            return ExtractBlobIds(await TryResultAsync<IReadOnlyList<Guid>>(jobs, jobId, cancellationToken));
        }

        private static async Task<T?> TryResultAsync<T>(IWitCloudJobs jobs, Guid jobId, CancellationToken cancellationToken)
        {
            try
            {
                return await jobs.GetResultAsync<T>(jobId, "result", cancellationToken);
            }
            catch
            {
                return default;
            }
        }

        private static List<Guid?> ExtractBlobIds(IEnumerable<Guid?>? values)
        {
            return values?
                .Where(me => me != null && me != Guid.Empty)
                .ToList()
                ?? [];
        }

        private static List<Guid?> ExtractBlobIds(IEnumerable<Guid>? values)
        {
            return values?
                .Where(me => me != Guid.Empty)
                .Select<Guid, Guid?>(me => me)
                .ToList()
                ?? [];
        }

        #endregion

        #region Properties

        [Inject]
        public IBridgeCloudConnectionService CloudConnectionService { get; set; } = null!;

        #endregion
    }
}
