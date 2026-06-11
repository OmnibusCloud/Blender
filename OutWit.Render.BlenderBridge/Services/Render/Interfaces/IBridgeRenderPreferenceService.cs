using OutWit.Render.BlenderBridge.Contracts;

namespace OutWit.Render.BlenderBridge.Services.Render.Interfaces
{
    /// <summary>
    /// Owns the persisted per-user render preferences (Phase 5): the bridge-side get/set surface the
    /// addon uses to seed its transient UI props and sticky-write used values after a submit.
    /// </summary>
    public interface IBridgeRenderPreferenceService
    {
        /// <summary>
        /// Returns the current persisted render preferences.
        /// </summary>
        Task<RenderSettingsResponse> GetRenderSettingsAsync();

        /// <summary>
        /// Persists the given render preferences snapshot. Returns true on success.
        /// </summary>
        Task<bool> SetRenderSettingsAsync(RenderSettingsResponse renderSettings);
    }
}
