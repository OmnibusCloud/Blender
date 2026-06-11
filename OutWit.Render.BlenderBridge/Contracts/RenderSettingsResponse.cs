using OutWit.Common.Abstract;
using OutWit.Common.Values;

namespace OutWit.Render.BlenderBridge.Contracts
{
    /// <summary>
    /// Addon-facing snapshot of the persisted per-user render preferences (Phase 5 bucket 1). Travels
    /// BOTH directions over the bridge REST: the addon seeds its transient bpy props from a get on
    /// connect, and sticky-writes the used values back via set on a successful submit (under the
    /// <see cref="RememberRenderSettings"/> master toggle). The bridge is the storage owner
    /// (Configuration/BridgeRenderSettings); this DTO is just the wire shape.
    /// </summary>
    public class RenderSettingsResponse : ModelBase
    {
        #region Model Base

        public override bool Is(ModelBase modelBase, double tolerance = DEFAULT_TOLERANCE)
        {
            if (modelBase is not RenderSettingsResponse other)
                return false;

            return RememberRenderSettings.Is(other.RememberRenderSettings)
                   && SplitFrame.Is(other.SplitFrame)
                   && TilesX.Is(other.TilesX)
                   && TilesY.Is(other.TilesY)
                   && TileOverlap.Is(other.TileOverlap)
                   && AnimResult.Is(other.AnimResult)
                   && VideoContainer.Is(other.VideoContainer)
                   && VideoCodec.Is(other.VideoCodec)
                   && LastGroupId.Is(other.LastGroupId)
                   && LastGroupName.Is(other.LastGroupName);
        }

        public override ModelBase Clone()
        {
            return new RenderSettingsResponse
            {
                RememberRenderSettings = RememberRenderSettings,
                SplitFrame = SplitFrame,
                TilesX = TilesX,
                TilesY = TilesY,
                TileOverlap = TileOverlap,
                AnimResult = AnimResult,
                VideoContainer = VideoContainer,
                VideoCodec = VideoCodec,
                LastGroupId = LastGroupId,
                LastGroupName = LastGroupName
            };
        }

        #endregion

        #region Properties

        public bool RememberRenderSettings { get; set; }

        public bool SplitFrame { get; set; }

        public int TilesX { get; set; }

        public int TilesY { get; set; }

        public int TileOverlap { get; set; }

        public string AnimResult { get; set; } = "";

        public string VideoContainer { get; set; } = "";

        public string VideoCodec { get; set; } = "";

        public string LastGroupId { get; set; } = "";

        public string LastGroupName { get; set; } = "";

        #endregion
    }
}
