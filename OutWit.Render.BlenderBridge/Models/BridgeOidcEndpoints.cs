namespace OutWit.Render.BlenderBridge.Models
{
    /// <summary>
    /// OIDC endpoints discovered from the configured identity issuer.
    /// </summary>
    public class BridgeOidcEndpoints
    {
        #region Properties

        public string TokenEndpoint { get; set; } = null!;

        public string AuthorizationEndpoint { get; set; } = null!;

        #endregion
    }
}
