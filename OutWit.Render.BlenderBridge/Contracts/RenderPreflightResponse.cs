using OutWit.Common.Abstract;
using OutWit.Common.Values;
using OutWit.Controller.Render.Model;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Result of running the bundled render preflight diagnostics for the current packaged runtime.
    /// </summary>
    public class RenderPreflightResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not RenderPreflightResponse other)
                return false;

            return Completed.Is(other.Completed)
                   && Status.Is(other.Status)
                   && Message.Is(other.Message)
                   && Result.Is(other.Result);
        }

        public override ModelBase Clone()
        {
            return new RenderPreflightResponse
            {
                Completed = Completed,
                Status = Status,
                Message = Message,
                Result = (RenderPreflightData?)Result?.Clone()
            };
        }

        #endregion

        #region Properties

        public bool Completed { get; set; }

        public string Status { get; set; } = null!;

        public string? Message { get; set; }

        public RenderPreflightData? Result { get; set; }

        #endregion
    }
}
