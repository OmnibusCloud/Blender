using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Result of launching the bundled RenderFrames script.
    /// </summary>
    public class RunRenderFramesResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not RunRenderFramesResponse other)
                return false;

            return JobId.Is(other.JobId)
                   && Status.Is(other.Status)
                   && Message.Is(other.Message);
        }

        public override ModelBase Clone()
        {
            return new RunRenderFramesResponse
            {
                JobId = JobId,
                Status = Status,
                Message = Message
            };
        }

        #endregion

        #region Properties

        public Guid JobId { get; set; }

        public string Status { get; set; } = null!;

        public string? Message { get; set; }

        #endregion
    }
}
