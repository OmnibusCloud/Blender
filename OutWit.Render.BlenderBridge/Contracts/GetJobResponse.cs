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

        public double OverallProgress { get; set; }

        public bool IsCompleted { get; set; }

        public Guid? ResultBlobId { get; set; }

        public List<Guid?> ResultBlobIds { get; set; } = [];

        public string? ErrorMessage { get; set; }

        #endregion
    }
}
