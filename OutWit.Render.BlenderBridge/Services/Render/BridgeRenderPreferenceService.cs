using Microsoft.Extensions.Logging;
using OutWit.Common.DependencyInjection;
using OutWit.Common.Settings.Interfaces;
using OutWit.Render.BlenderBridge.Configuration;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Services.Render.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Render
{
    /// <summary>
    /// Bridge-side persisted render preferences (Phase 5). Thin mapping between the wire snapshot
    /// (<see cref="RenderSettingsResponse"/>) and the per-user settings store
    /// (<see cref="BridgeRenderSettings"/> over OutWit.Common.Settings); a set persists immediately.
    /// The bridge stores what it is given — value policy (clamps, enum choices) lives in the addon UI.
    /// </summary>
    [InjectableHost]
    public partial class BridgeRenderPreferenceService : IBridgeRenderPreferenceService
    {
        #region IBridgeRenderPreferenceService

        public Task<RenderSettingsResponse> GetRenderSettingsAsync()
        {
            return Task.FromResult(new RenderSettingsResponse
            {
                RememberRenderSettings = RenderSettings.RememberRenderSettings,
                SplitFrame = RenderSettings.SplitFrame,
                TilesX = RenderSettings.TilesX,
                TilesY = RenderSettings.TilesY,
                TileOverlap = RenderSettings.TileOverlap,
                AnimResult = RenderSettings.AnimResult,
                VideoContainer = RenderSettings.VideoContainer,
                VideoCodec = RenderSettings.VideoCodec,
                LastGroupId = RenderSettings.LastGroupId,
                LastGroupName = RenderSettings.LastGroupName
            });
        }

        public Task<bool> SetRenderSettingsAsync(RenderSettingsResponse renderSettings)
        {
            if (renderSettings == null)
                throw new InvalidOperationException("Render settings payload is required.");

            RenderSettings.RememberRenderSettings = renderSettings.RememberRenderSettings;
            RenderSettings.SplitFrame = renderSettings.SplitFrame;
            RenderSettings.TilesX = renderSettings.TilesX;
            RenderSettings.TilesY = renderSettings.TilesY;
            RenderSettings.TileOverlap = renderSettings.TileOverlap;
            RenderSettings.AnimResult = renderSettings.AnimResult ?? "";
            RenderSettings.VideoContainer = renderSettings.VideoContainer ?? "";
            RenderSettings.VideoCodec = renderSettings.VideoCodec ?? "";
            RenderSettings.LastGroupId = renderSettings.LastGroupId ?? "";
            RenderSettings.LastGroupName = renderSettings.LastGroupName ?? "";

            SettingsManager.Save();

            Logger.LogInformation("Render preferences persisted (remember={Remember}).",
                renderSettings.RememberRenderSettings);

            return Task.FromResult(true);
        }

        #endregion

        #region Properties

        [Inject]
        public BridgeRenderSettings RenderSettings { get; set; } = null!;

        [Inject]
        public ISettingsManager SettingsManager { get; set; } = null!;

        [Inject]
        public ILogger<BridgeRenderPreferenceService> Logger { get; set; } = null!;

        #endregion
    }
}
