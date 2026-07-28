using OutWit.Cloud.Auth.Sessions;

namespace OutWit.Render.BlenderBridge.Services.Auth.Interfaces
{
    /// <summary>
    /// Exposes the shared encrypted session store the bridge persists its login session to.
    /// </summary>
    public interface IBridgeSessionStore
    {
        /// <summary>
        /// The shared OutWit.Cloud.Auth session store, bound to the bridge's per-OS-user session file.
        /// </summary>
        SessionStore Store { get; }
    }
}
