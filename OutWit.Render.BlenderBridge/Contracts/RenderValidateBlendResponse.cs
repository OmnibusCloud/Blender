using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Result of running the bundled RenderValidateBlend script for one uploaded scene blob.
    /// </summary>
    public class RenderValidateBlendResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not RenderValidateBlendResponse other)
                return false;

            return JobId.Is(other.JobId)
                   && Completed.Is(other.Completed)
                   && IsValid.Is(other.IsValid)
                   && Issues.SequenceEqual(other.Issues)
                   && Warnings.SequenceEqual(other.Warnings)
                   && Status.Is(other.Status)
                   && Message.Is(other.Message);
        }

        public override ModelBase Clone()
        {
            return new RenderValidateBlendResponse
            {
                JobId = JobId,
                Completed = Completed,
                IsValid = IsValid,
                Issues = [.. Issues],
                Warnings = [.. Warnings],
                Status = Status,
                Message = Message
            };
        }

        #endregion

        #region Properties

        public Guid JobId { get; set; }

        public bool Completed { get; set; }

        public bool IsValid { get; set; }

        public List<string> Issues { get; set; } = [];

        public List<string> Warnings { get; set; } = [];

        public string Status { get; set; } = null!;

        public string? Message { get; set; }

        #endregion
    }
}
