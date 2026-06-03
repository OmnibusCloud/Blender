using Microsoft.Extensions.DependencyInjection;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Auth
{
    /// <summary>
    /// Factory for creating bridge authorization callback listeners.
    /// </summary>
    [InjectableHost]
    public partial class BridgeAuthorizationCallbackListenerFactory : IBridgeAuthorizationCallbackListenerFactory
    {
        #region IBridgeAuthorizationCallbackListenerFactory

        public IBridgeAuthorizationCallbackListener Create()
        {
            return ActivatorUtilities.CreateInstance<BridgeAuthorizationCallbackListenerLoopback>(Services);
        }

        #endregion

        #region Properties

        #endregion
    }
}
