using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Result of launching the bundled RenderStillTiled script.
    /// </summary>
    public class RunRenderStillTiledResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not RunRenderStillTiledResponse other)
                return false;

            return JobId.Is(other.JobId)
                   && Status.Is(other.Status)
                   && Message.Is(other.Message);
        }

        public override ModelBase Clone()
        {
            return new RunRenderStillTiledResponse
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
