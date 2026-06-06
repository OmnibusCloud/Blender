using OutWit.Common.Abstract;
using OutWit.Common.Collections;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Addon-facing summary of one bridge-launched cloud job.
    /// </summary>
    public class GetJobResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not GetJobResponse other)
                return false;

            return JobId.Is(other.JobId)
                   && ScriptName.Is(other.ScriptName)
                   && Status.Is(other.Status)
                   && OverallProgress.Is(other.OverallProgress)
                   && DistributedProgress.Is(other.DistributedProgress)
                   && IsCompleted.Is(other.IsCompleted)
                   && ResultBlobId.Is(other.ResultBlobId)
                   && ResultBlobIds.Is(other.ResultBlobIds)
                   && ErrorMessage.Is(other.ErrorMessage);
        }

        public override ModelBase Clone()
        {
            return new GetJobResponse
            {
                JobId = JobId,
                ScriptName = ScriptName,
                Status = Status,
                OverallProgress = OverallProgress,
                DistributedProgress = DistributedProgress,
                IsCompleted = IsCompleted,
                ResultBlobId = ResultBlobId,
                ResultBlobIds = [.. ResultBlobIds],
                ErrorMessage = ErrorMessage
            };
        }

        #endregion

        #region Properties

        public Guid JobId { get; set; }

        public string ScriptName { get; set; } = null!;

        public string Status { get; set; } = null!;

        /// <summary>Coarse engine stage-based progress (0.0 to 1.0).</summary>
        public double OverallProgress { get; set; }

        /// <summary>Fine-grained distributed "computation" progress (0.0 to 1.0); 0 when the job has no
        /// distributed work.</summary>
        public double DistributedProgress { get; set; }

        public bool IsCompleted { get; set; }

        public Guid? ResultBlobId { get; set; }

        public List<Guid?> ResultBlobIds { get; set; } = [];

        public string? ErrorMessage { get; set; }

        #endregion
    }
}
