using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Result of requesting interactive sign-in from the local bridge.
    /// </summary>
    public class BeginSignInResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not BeginSignInResponse other)
                return false;

            return Started.Is(other.Started)
                   && RequiresBrowser.Is(other.RequiresBrowser)
                   && Message.Is(other.Message);
        }

        public override ModelBase Clone()
        {
            return new BeginSignInResponse
            {
                Started = Started,
                RequiresBrowser = RequiresBrowser,
                Message = Message
            };
        }

        #endregion

        #region Properties

        public bool Started { get; set; }

        public bool RequiresBrowser { get; set; }

        public string? Message { get; set; }

        #endregion
    }
}
