using OutWit.Render.BlenderBridge.Contracts;

namespace OutWit.Render.BlenderBridge.Services.Cloud.Interfaces
{
    /// <summary>
    /// Owns bridge-side execution scope discovery and validation.
    /// </summary>
    public interface IBridgeExecutionScopeService
    {
        /// <summary>
        /// Returns execution scope options available to the current bridge user session.
        /// </summary>
        Task<ExecutionScopeOptionsResponse> GetExecutionScopeOptionsAsync(CancellationToken cancellationToken = default);
    }
}
