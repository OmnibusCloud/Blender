using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Models
{
    /// <summary>
    /// Local bridge connection context shared with the addon out of band.
    /// </summary>
    public class BridgeLocalConnectionContext : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not BridgeLocalConnectionContext other)
                return false;

            return LocalRestUrl.Is(other.LocalRestUrl)
                   && IsSecretRequired.Is(other.IsSecretRequired)
                   && SessionSecret.Is(other.SessionSecret)
                   && BridgeProcessId.Is(other.BridgeProcessId)
                   && CreatedUtc.Is(other.CreatedUtc);
        }

        public override ModelBase Clone()
        {
            return new BridgeLocalConnectionContext
            {
                LocalRestUrl = LocalRestUrl,
                IsSecretRequired = IsSecretRequired,
                SessionSecret = SessionSecret,
                BridgeProcessId = BridgeProcessId,
                CreatedUtc = CreatedUtc
            };
        }

        #endregion

        #region Properties

        public string LocalRestUrl { get; set; } = null!;

        public bool IsSecretRequired { get; set; }

        public string? SessionSecret { get; set; }

        public int BridgeProcessId { get; set; }

        public string CreatedUtc { get; set; } = null!;

        #endregion
    }
}
