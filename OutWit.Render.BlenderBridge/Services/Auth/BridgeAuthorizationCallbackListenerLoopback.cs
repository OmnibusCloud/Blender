using System.Net;
using System.Text;
using Microsoft.Extensions.Logging;
using OutWit.Common.DependencyInjection;
using OutWit.Render.BlenderBridge.Services.Auth.Interfaces;

namespace OutWit.Render.BlenderBridge.Services.Auth
{
    /// <summary>
    /// Loopback HTTP listener for the OAuth authorization-code callback.
    /// </summary>
    public class BridgeAuthorizationCallbackListenerLoopback : IBridgeAuthorizationCallbackListener
    {
        #region Constants

        private static readonly int[] PORTS = [17892, 17893, 17894];
        private const string CALLBACK_PATH = "/callback";

        private const string SUCCESS_HTML = """
            <!DOCTYPE html>
            <html>
            <head><meta charset=\"utf-8\"/><title>Authentication Successful</title></head>
            <body><h2>Authentication Successful</h2><p>You can close this tab and return to Blender.</p></body>
            </html>
            """;

        private const string ERROR_HTML = """
            <!DOCTYPE html>
            <html>
            <head><meta charset=\"utf-8\"/><title>Authentication Failed</title></head>
            <body><h2>Authentication Failed</h2><p>{0}</p></body>
            </html>
            """;

        #endregion

        #region Fields

        private readonly HttpListener m_listener;

        #endregion

        #region Constructors

        public BridgeAuthorizationCallbackListenerLoopback(IServiceProvider services)
        {
            Services = services;
            m_listener = new HttpListener();
        }

        #endregion

        #region IBridgeAuthorizationCallbackListener

        public string? TryStart()
        {
            foreach (var port in PORTS)
            {
                var prefix = $"http://127.0.0.1:{port}{CALLBACK_PATH}/";
                try
                {
                    m_listener.Prefixes.Clear();
                    m_listener.Prefixes.Add(prefix);
                    m_listener.Start();

                    RedirectUri = $"http://127.0.0.1:{port}{CALLBACK_PATH}";
                    Logger.LogInformation("Bridge loopback listener started on port {Port}", port);
                    return RedirectUri;
                }
                catch (HttpListenerException)
                {
                    Logger.LogWarning("Bridge loopback port {Port} is in use, trying next", port);
                }
            }

            Logger.LogError("Bridge failed to bind any loopback auth callback port.");
            return null;
        }

        public async Task<string?> WaitForCallbackAsync(string expectedState, string? completionUrl, CancellationToken cancellationToken)
        {
            using var registration = cancellationToken.Register(Stop);

            try
            {
                var context = await m_listener.GetContextAsync();
                var query = context.Request.QueryString;
                var error = query["error"];
                var state = query["state"];
                var code = query["code"];

                if (!string.IsNullOrEmpty(error))
                {
                    var description = query["error_description"] ?? error;
                    Logger.LogWarning("Bridge authorization error: {Error} - {Description}", error, description);
                    await RespondAsync(context, completionUrl, isError: true, errorDetail: description);
                    return null;
                }

                if (state != expectedState)
                {
                    Logger.LogWarning("Bridge authorization state mismatch: expected {ExpectedState}, got {ActualState}", expectedState, state);
                    await RespondAsync(context, completionUrl, isError: true, errorDetail: "Security validation failed (state mismatch).");
                    return null;
                }

                if (string.IsNullOrWhiteSpace(code))
                {
                    Logger.LogWarning("Bridge authorization callback did not contain a code.");
                    await RespondAsync(context, completionUrl, isError: true, errorDetail: "No authorization code received.");
                    return null;
                }

                Logger.LogInformation("Bridge authorization code received successfully.");
                await RespondAsync(context, completionUrl, isError: false);
                return code;
            }
            catch (HttpListenerException) when (cancellationToken.IsCancellationRequested)
            {
                Logger.LogInformation("Bridge loopback listener cancelled.");
                return null;
            }
            catch (ObjectDisposedException) when (cancellationToken.IsCancellationRequested)
            {
                return null;
            }
            catch (Exception ex)
            {
                Logger.LogError(ex, "Bridge auth callback listener failed while waiting for the browser redirect.");
                return null;
            }
        }

        #endregion

        #region Tools

        private void Stop()
        {
            try
            {
                m_listener.Stop();
            }
            catch
            {
            }
        }

        /// <summary>
        /// Sends the browser onward after the callback. When a completion URL is supplied, the
        /// browser is redirected to the shared WitIdentity completion page (with "status=error"
        /// appended on failure) so every native client shows the same branded page. Otherwise an
        /// inline HTML page is rendered as a fallback. The raw error detail stays in the logs only.
        /// </summary>
        private static async Task RespondAsync(HttpListenerContext context, string? completionUrl, bool isError, string? errorDetail = null)
        {
            if (!string.IsNullOrWhiteSpace(completionUrl))
            {
                var location = isError ? AppendStatusError(completionUrl) : completionUrl;
                context.Response.Redirect(location);
                context.Response.Close();
                return;
            }

            var html = isError
                ? string.Format(ERROR_HTML, WebUtility.HtmlEncode(errorDetail ?? "Authentication failed."))
                : SUCCESS_HTML;
            await WriteResponseAsync(context, html);
        }

        private static string AppendStatusError(string completionUrl)
        {
            return completionUrl.Contains('?')
                ? $"{completionUrl}&status=error"
                : $"{completionUrl}?status=error";
        }

        private static async Task WriteResponseAsync(HttpListenerContext context, string html)
        {
            var buffer = Encoding.UTF8.GetBytes(html);
            context.Response.ContentType = "text/html; charset=utf-8";
            context.Response.ContentLength64 = buffer.Length;
            context.Response.StatusCode = 200;
            await context.Response.OutputStream.WriteAsync(buffer);
            context.Response.Close();
        }

        #endregion

        #region IDisposable

        public void Dispose()
        {
            Stop();
            m_listener.Close();
        }

        #endregion

        #region Properties

        protected IServiceProvider Services { get; }

        [Inject]
        public ILogger<BridgeAuthorizationCallbackListenerLoopback> Logger { get; set; } = null!;

        public string? RedirectUri { get; private set; }

        #endregion
    }
}
