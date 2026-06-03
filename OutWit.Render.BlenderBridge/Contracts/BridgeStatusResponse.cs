using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Local bridge health and session summary exposed to the Blender addon.
    /// </summary>
    public class BridgeStatusResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not BridgeStatusResponse other)
                return false;

            return BridgeVersion.Is(other.BridgeVersion)
                   && IsSignedIn.Is(other.IsSignedIn)
                   && IsConnectedToCloud.Is(other.IsConnectedToCloud)
                   && CurrentUserDisplayName.Is(other.CurrentUserDisplayName)
                   && CurrentUserId.Is(other.CurrentUserId)
                   && LastError.Is(other.LastError);
        }

        public override ModelBase Clone()
        {
            return new BridgeStatusResponse
            {
                BridgeVersion = BridgeVersion,
                IsSignedIn = IsSignedIn,
                IsConnectedToCloud = IsConnectedToCloud,
                CurrentUserDisplayName = CurrentUserDisplayName,
                CurrentUserId = CurrentUserId,
                LastError = LastError
            };
        }

        #endregion

        #region Properties

        public string BridgeVersion { get; set; } = null!;

        public bool IsSignedIn { get; set; }

        public bool IsConnectedToCloud { get; set; }

        public string? CurrentUserDisplayName { get; set; }

        public string? CurrentUserId { get; set; }

        public string? LastError { get; set; }

        #endregion
    }
}
