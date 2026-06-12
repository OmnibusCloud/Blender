using OutWit.Common.Settings.Aspects;
using OutWit.Common.Settings.Configuration;
using OutWit.Common.Settings.Interfaces;

namespace OutWit.Render.BlenderBridge.Configuration
{
    /// <summary>
    /// Per-OS-user render PREFERENCES — the "remember last render settings" buckets (Phase 5). These are
    /// the artist's sticky working habits that have no other source of truth: the split/tiling choice,
    /// the animation result kind + video container/codec, and the last render target (with a name so the
    /// UI can show it even if the group later disappears). They are written by the addon (via the bridge
    /// REST get/set) on a successful submit, under the <see cref="RememberRenderSettings"/> master toggle.
    ///
    /// NON-secret only: the OIDC refresh token is NOT here — it stays in its own DPAPI-encrypted store
    /// (<see cref="Services.Auth.BridgeSessionStore"/>). Frame range / resolution / image format / fps are
    /// NOT here either — those are read live from the scene's Output Properties (single source of truth).
    /// </summary>
    public class BridgeRenderSettings : SettingsContainer
    {
        #region Constructors

        public BridgeRenderSettings(ISettingsManager manager) : base(manager)
        {
        }

        #endregion

        #region Render

        /// <summary>Master toggle — when off, the addon stops seeding/sticky-writing these prefs.</summary>
        [Setting("Render")]
        public virtual bool RememberRenderSettings { get; set; }

        /// <summary>Image output: split a single frame across machines (tiled still).</summary>
        [Setting("Render")]
        public virtual bool SplitFrame { get; set; }

        [Setting("Render")]
        public virtual int TilesX { get; set; }

        [Setting("Render")]
        public virtual int TilesY { get; set; }

        [Setting("Render")]
        public virtual int TileOverlap { get; set; }

        /// <summary>Animation deliverable: "Sequence" or "Video".</summary>
        [Setting("Render")]
        public virtual string AnimResult { get; set; } = null!;

        [Setting("Render")]
        public virtual string VideoContainer { get; set; } = null!;

        [Setting("Render")]
        public virtual string VideoCodec { get; set; } = null!;

        /// <summary>CRF quality for the CRF-driven video presets (ignored by ProRes).</summary>
        [Setting("Render")]
        public virtual int VideoCrf { get; set; }

        #endregion

        #region Target

        /// <summary>Last selected render target group id (empty = all nodes). Sticky fallback.</summary>
        [Setting("Target")]
        public virtual string LastGroupId { get; set; } = null!;

        /// <summary>Display name of the last target group, so the UI can show it even if it disappears.</summary>
        [Setting("Target")]
        public virtual string LastGroupName { get; set; } = null!;

        #endregion
    }
}
