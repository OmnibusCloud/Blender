using System.Reflection;
using Microsoft.Extensions.Logging;
using OutWit.Controller.Render.Model;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Contracts;
using OutWit.Render.BlenderBridge.Channels.Interfaces;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;
using OutWit.Render.BlenderBridge.Services.Cloud.Interfaces;
using OutWit.Render.BlenderBridge.Services.Hosting.Interfaces;
using OutWit.Render.BlenderBridge.Services.Render.Interfaces;

namespace OutWit.Render.BlenderBridge.Channels
{
    /// <summary>
    /// First-slice local bridge channel implementation.
    /// </summary>
    [InjectableHost]
    public partial class BlenderBridgeChannel : IBlenderBridgeChannel
    {
        #region IBlenderBridgeChannel

        public async Task<BridgeStatusResponse> GetBridgeStatusAsync()
        {
            var session = await SessionService.GetSessionStateAsync();
            var connected = await CloudConnectionService.IsConnectedAsync();

            Logger.LogInformation("Bridge status requested. SignedIn={IsSignedIn}, ConnectedToCloud={ConnectedToCloud}, UserId={UserId}, LastError={LastError}",
                session.IsSignedIn,
                connected,
                session.UserId,
                session.LastError);

            return new BridgeStatusResponse
            {
                BridgeVersion = Assembly.GetExecutingAssembly().GetName().Version?.ToString() ?? "0.0.0",
                IsSignedIn = session.IsSignedIn,
                IsConnectedToCloud = connected,
                CurrentUserDisplayName = session.DisplayName,
                CurrentUserId = session.UserId,
                LastError = session.LastError
            };
        }

        public Task<BeginSignInResponse> BeginSignInAsync()
        {
            return SessionService.BeginSignInAsync();
        }

        public Task<bool> SignOutAsync()
        {
            return SessionService.SignOutAsync();
        }

        public async Task<SessionStateResponse> GetSessionStateAsync()
        {
            var session = await SessionService.GetSessionStateAsync();

            Logger.LogInformation("Bridge session-state response requested. SignedIn={IsSignedIn}, CanLaunch={CanLaunch}, UserId={UserId}, LastError={LastError}",
                session.IsSignedIn,
                session.CanLaunch,
                session.UserId,
                session.LastError);

            return new SessionStateResponse
            {
                IsSignedIn = session.IsSignedIn,
                DisplayName = session.DisplayName,
                UserId = session.UserId,
                CanLaunch = session.CanLaunch,
                NeedsInteractiveLogin = session.NeedsInteractiveLogin,
                LastError = session.LastError
            };
        }

        public Task<ExecutionScopeOptionsResponse> GetExecutionScopeOptionsAsync()
        {
            return ExecutionScopeService.GetExecutionScopeOptionsAsync();
        }

        public Task<AcquireLeaseResponse> AcquireLeaseAsync(int ownerProcessId, string leaseId, string? addonVersion = null)
        {
            return LeaseService.AcquireLeaseAsync(ownerProcessId, leaseId, addonVersion);
        }

        public Task<bool> PingLeaseAsync(string leaseId)
        {
            return LeaseService.PingLeaseAsync(leaseId);
        }

        public Task<bool> ReleaseLeaseAsync(string leaseId)
        {
            return LeaseService.ReleaseLeaseAsync(leaseId);
        }

        public Task<UploadBlendResponse> UploadBlendAsync(string filePath)
        {
            return BlobTransferService.UploadBlendAsync(filePath);
        }

        public Task<UploadBlendResponse> UploadFileAsync(string filePath)
        {
            return BlobTransferService.UploadFileAsync(filePath);
        }

        public Task<RenderValidateBlendResponse> RunRenderValidateBlendAsync(Guid sceneBlobId)
        {
            return RenderLaunchService.RunRenderValidateBlendAsync(sceneBlobId);
        }

        public Task<RenderValidateBlendResponse> RunRenderValidateBlendAsync(Guid sceneBlobId, List<RenderSceneAttachmentRefData> attachedFiles)
        {
            return RenderLaunchService.RunRenderValidateBlendAsync(sceneBlobId, attachedFiles);
        }

        public Task<RenderPreflightResponse> RunRenderPreflightAsync(
            int frame,
            int startFrame,
            int endFrame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            VideoOptionsData video)
        {
            return RenderLaunchService.RunRenderPreflightAsync(
                frame,
                startFrame,
                endFrame,
                tilesX,
                tilesY,
                options,
                tileOptions,
                video);
        }

        public Task<RunRenderStillResponse> RunRenderStillAsync(Guid sceneBlobId, int frame, RenderOptionsData options)
        {
            return RenderLaunchService.RunRenderStillAsync(sceneBlobId, frame, options);
        }

        public Task<RunRenderStillResponse> RunRenderStillAsync(Guid sceneBlobId, int frame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles)
        {
            return RenderLaunchService.RunRenderStillAsync(sceneBlobId, frame, options, attachedFiles);
        }

        public Task<RunRenderStillResponse> RunRenderStillAsync(Guid sceneBlobId, int frame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedClientGroupId)
        {
            return RenderLaunchService.RunRenderStillAsync(sceneBlobId, frame, options, attachedFiles, selectedClientGroupId);
        }

        public Task<RunRenderStillTiledResponse> RunRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions)
        {
            return RenderLaunchService.RunRenderStillTiledAsync(sceneBlobId, frame, tilesX, tilesY, options, tileOptions);
        }

        public Task<RunRenderStillTiledResponse> RunRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            List<RenderSceneAttachmentRefData> attachedFiles)
        {
            return RenderLaunchService.RunRenderStillTiledAsync(sceneBlobId, frame, tilesX, tilesY, options, tileOptions, attachedFiles);
        }

        public Task<RunRenderStillTiledResponse> RunRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            List<RenderSceneAttachmentRefData> attachedFiles,
            Guid selectedClientGroupId)
        {
            return RenderLaunchService.RunRenderStillTiledAsync(sceneBlobId, frame, tilesX, tilesY, options, tileOptions, attachedFiles, selectedClientGroupId);
        }

        public Task<RunRenderFramesResponse> RunRenderFramesAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options)
        {
            return RenderLaunchService.RunRenderFramesAsync(sceneBlobId, startFrame, endFrame, options);
        }

        public Task<RunRenderFramesResponse> RunRenderFramesAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles)
        {
            return RenderLaunchService.RunRenderFramesAsync(sceneBlobId, startFrame, endFrame, options, attachedFiles);
        }

        public Task<RunRenderFramesResponse> RunRenderFramesAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedClientGroupId)
        {
            return RenderLaunchService.RunRenderFramesAsync(sceneBlobId, startFrame, endFrame, options, attachedFiles, selectedClientGroupId);
        }

        public Task<RunRenderVideoResponse> RunRenderVideoAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, VideoOptionsData video)
        {
            return RenderLaunchService.RunRenderVideoAsync(sceneBlobId, startFrame, endFrame, options, video);
        }

        public Task<RunRenderVideoResponse> RunRenderVideoAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, VideoOptionsData video, List<RenderSceneAttachmentRefData> attachedFiles)
        {
            return RenderLaunchService.RunRenderVideoAsync(sceneBlobId, startFrame, endFrame, options, video, attachedFiles);
        }

        public Task<RunRenderVideoResponse> RunRenderVideoAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, VideoOptionsData video, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedClientGroupId)
        {
            return RenderLaunchService.RunRenderVideoAsync(sceneBlobId, startFrame, endFrame, options, video, attachedFiles, selectedClientGroupId);
        }

        public Task<RunRenderStillResponse> RunBakeAndRenderStillAsync(Guid sceneBlobId, int frame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles)
        {
            return RenderLaunchService.RunBakeAndRenderStillAsync(sceneBlobId, frame, options, attachedFiles);
        }

        public Task<RunRenderStillResponse> RunBakeAndRenderStillAsync(Guid sceneBlobId, int frame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedClientGroupId)
        {
            return RenderLaunchService.RunBakeAndRenderStillAsync(sceneBlobId, frame, options, attachedFiles, selectedClientGroupId);
        }

        public Task<RunRenderStillTiledResponse> RunBakeAndRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            List<RenderSceneAttachmentRefData> attachedFiles)
        {
            return RenderLaunchService.RunBakeAndRenderStillTiledAsync(sceneBlobId, frame, tilesX, tilesY, options, tileOptions, attachedFiles);
        }

        public Task<RunRenderStillTiledResponse> RunBakeAndRenderStillTiledAsync(
            Guid sceneBlobId,
            int frame,
            int tilesX,
            int tilesY,
            RenderOptionsData options,
            TileOptionsData tileOptions,
            List<RenderSceneAttachmentRefData> attachedFiles,
            Guid selectedClientGroupId)
        {
            return RenderLaunchService.RunBakeAndRenderStillTiledAsync(sceneBlobId, frame, tilesX, tilesY, options, tileOptions, attachedFiles, selectedClientGroupId);
        }

        public Task<RunRenderFramesResponse> RunBakeAndRenderFramesAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles)
        {
            return RenderLaunchService.RunBakeAndRenderFramesAsync(sceneBlobId, startFrame, endFrame, options, attachedFiles);
        }

        public Task<RunRenderFramesResponse> RunBakeAndRenderFramesAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedClientGroupId)
        {
            return RenderLaunchService.RunBakeAndRenderFramesAsync(sceneBlobId, startFrame, endFrame, options, attachedFiles, selectedClientGroupId);
        }

        public Task<RunRenderVideoResponse> RunBakeAndRenderVideoAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, VideoOptionsData video, List<RenderSceneAttachmentRefData> attachedFiles)
        {
            return RenderLaunchService.RunBakeAndRenderVideoAsync(sceneBlobId, startFrame, endFrame, options, video, attachedFiles);
        }

        public Task<RunRenderVideoResponse> RunBakeAndRenderVideoAsync(Guid sceneBlobId, int startFrame, int endFrame, RenderOptionsData options, VideoOptionsData video, List<RenderSceneAttachmentRefData> attachedFiles, Guid selectedClientGroupId)
        {
            return RenderLaunchService.RunBakeAndRenderVideoAsync(sceneBlobId, startFrame, endFrame, options, video, attachedFiles, selectedClientGroupId);
        }

        public Task<GetJobResponse> GetJobAsync(Guid jobId)
        {
            return JobQueryService.GetJobAsync(jobId);
        }

        public Task<bool> CancelJobAsync(Guid jobId)
        {
            return JobQueryService.CancelJobAsync(jobId);
        }

        public Task<DownloadResultResponse> DownloadResultAsync(Guid jobId)
        {
            return DownloadService.DownloadResultAsync(jobId);
        }

        public Task<RenderSettingsResponse> GetRenderSettingsAsync()
        {
            return RenderPreferenceService.GetRenderSettingsAsync();
        }

        public Task<bool> SetRenderSettingsAsync(RenderSettingsResponse renderSettings)
        {
            return RenderPreferenceService.SetRenderSettingsAsync(renderSettings);
        }

        #endregion

        #region Properties

        [Inject]
        public IBridgeSessionService SessionService { get; set; } = null!;

        [Inject]
        public IBridgeCloudConnectionService CloudConnectionService { get; set; } = null!;

        [Inject]
        public IBridgeExecutionScopeService ExecutionScopeService { get; set; } = null!;

        [Inject]
        public IBridgeBlobTransferService BlobTransferService { get; set; } = null!;

        [Inject]
        public IBridgeLeaseService LeaseService { get; set; } = null!;

        [Inject]
        public IBridgeRenderLaunchService RenderLaunchService { get; set; } = null!;

        [Inject]
        public IBridgeJobQueryService JobQueryService { get; set; } = null!;

        [Inject]
        public IBridgeRenderPreferenceService RenderPreferenceService { get; set; } = null!;

        [Inject]
        public IBridgeDownloadService DownloadService { get; set; } = null!;

        [Inject]
        public ILogger<BlenderBridgeChannel> Logger { get; set; } = null!;

        #endregion
    }
}
