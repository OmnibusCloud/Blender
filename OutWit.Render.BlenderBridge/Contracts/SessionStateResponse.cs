using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Addon-facing current session state for the bridge user session.
    /// </summary>
    public class SessionStateResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not SessionStateResponse other)
                return false;

            return IsSignedIn.Is(other.IsSignedIn)
                   && DisplayName.Is(other.DisplayName)
                   && UserId.Is(other.UserId)
                   && CanLaunch.Is(other.CanLaunch)
                   && NeedsInteractiveLogin.Is(other.NeedsInteractiveLogin)
                   && LastError.Is(other.LastError);
        }

        public override ModelBase Clone()
        {
            return new SessionStateResponse
            {
                IsSignedIn = IsSignedIn,
                DisplayName = DisplayName,
                UserId = UserId,
                CanLaunch = CanLaunch,
                NeedsInteractiveLogin = NeedsInteractiveLogin,
                LastError = LastError
            };
        }

        #endregion

        #region Properties

        public bool IsSignedIn { get; set; }

        public string? DisplayName { get; set; }

        public string? UserId { get; set; }

        public bool CanLaunch { get; set; }

        public bool NeedsInteractiveLogin { get; set; }

        public string? LastError { get; set; }

        #endregion
    }
}
