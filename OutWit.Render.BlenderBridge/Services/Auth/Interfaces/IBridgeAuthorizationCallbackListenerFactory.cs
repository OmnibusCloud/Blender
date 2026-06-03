namespace OutWit.Render.BlenderBridge.Services.Auth.Interfaces
{
    /// <summary>
    /// Creates authorization callback listeners for bridge authentication flows.
    /// </summary>
    public interface IBridgeAuthorizationCallbackListenerFactory
    {
        /// <summary>
        /// Creates a new callback listener instance.
        /// </summary>
        IBridgeAuthorizationCallbackListener Create();
    }
}
