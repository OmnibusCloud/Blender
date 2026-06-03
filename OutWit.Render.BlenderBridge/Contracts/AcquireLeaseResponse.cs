using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Result of acquiring or refreshing the local addon-owned bridge lease.
    /// </summary>
    public class AcquireLeaseResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not AcquireLeaseResponse other)
                return false;

            return LeaseAccepted.Is(other.LeaseAccepted)
                   && LeaseId.Is(other.LeaseId)
                   && HeartbeatIntervalSeconds.Is(other.HeartbeatIntervalSeconds)
                   && LeaseTimeoutSeconds.Is(other.LeaseTimeoutSeconds)
                   && Message.Is(other.Message);
        }

        public override ModelBase Clone()
        {
            return new AcquireLeaseResponse
            {
                LeaseAccepted = LeaseAccepted,
                LeaseId = LeaseId,
                HeartbeatIntervalSeconds = HeartbeatIntervalSeconds,
                LeaseTimeoutSeconds = LeaseTimeoutSeconds,
                Message = Message
            };
        }

        #endregion

        #region Properties

        public bool LeaseAccepted { get; set; }

        public string LeaseId { get; set; } = null!;

        public int HeartbeatIntervalSeconds { get; set; }

        public int LeaseTimeoutSeconds { get; set; }

        public string? Message { get; set; }

        #endregion
    }
}
