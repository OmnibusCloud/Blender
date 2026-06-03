using System.Net.Http.Json;
using System.Text.Json;
using OutWit.Communication.Responses;
using OutWit.Render.BlenderBridge.Models;

namespace OutWit.Render.BlenderBridge.Tests.Infrastructure.Transport
{
    internal static class BridgeRestTestUtils
    {
        private static readonly JsonSerializerOptions REQUEST_JSON_OPTIONS = new()
        {
            PropertyNamingPolicy = null
        };

        #region Tools

        public static string CreateTempDirectory()
        {
            var path = Path.Combine(Path.GetTempPath(), "BridgeRestIntegrationTests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(path);
            return path;
        }

        public static async Task<TResponse> SendGetAsync<TResponse>(HttpClient http, string baseUrl, string methodName)
        {
            return await SendGetAsync<TResponse>(http, baseUrl, methodName, []);
        }

        public static async Task<TResponse> SendGetAsync<TResponse>(HttpClient http, string baseUrl, string methodName, params string[] parameters)
        {
            var response = await SendRawGetAsync(http, baseUrl, methodName, parameters);

            Assert.That(response, Is.Not.Null, $"Bridge REST call returned no response for {methodName}.");
            Assert.That(response!.IsSuccess(), Is.True, response.ErrorMessage);
            Assert.That(response.Data, Is.Not.Null.And.Not.Empty, $"Bridge REST call returned no payload for {methodName}.");

            var payload = JsonSerializer.Deserialize<TResponse>(response.Data!);
            Assert.That(payload, Is.Not.Null, $"Bridge REST payload could not be deserialized for {methodName}.");
            return payload!;
        }

        public static async Task<TResponse> SendPostAsync<TResponse>(HttpClient http, string baseUrl, string methodName, params object?[] payload)
        {
            var response = await SendRawPostAsync(http, baseUrl, methodName, payload);

            Assert.That(response, Is.Not.Null, $"Bridge REST call returned no response for {methodName}.");
            Assert.That(response!.IsSuccess(), Is.True, response.ErrorMessage);
            Assert.That(response.Data, Is.Not.Null.And.Not.Empty, $"Bridge REST call returned no payload for {methodName}.");

            var value = JsonSerializer.Deserialize<TResponse>(response.Data!);
            Assert.That(value, Is.Not.Null, $"Bridge REST payload could not be deserialized for {methodName}.");
            return value!;
        }

        public static async Task<WitResponse> SendRawGetAsync(HttpClient http, string baseUrl, string methodName)
        {
            return await SendRawGetAsync(http, baseUrl, methodName, []);
        }

        public static async Task<WitResponse> SendRawGetAsync(HttpClient http, string baseUrl, string methodName, params string[] parameters)
        {
            var url = BuildGetUrl(baseUrl, methodName, parameters);
            using var responseMessage = await http.GetAsync(url);
            var response = await responseMessage.Content.ReadFromJsonAsync<WitResponse>();

            Assert.That(response, Is.Not.Null, $"Bridge REST call returned no response for {methodName}.");
            return response!;
        }

        public static async Task<WitResponse> SendRawPostAsync(HttpClient http, string baseUrl, string methodName, params object?[] payload)
        {
            var url = $"{baseUrl.TrimEnd('/')}/{methodName}";
            var body = payload
                .Select((me, index) => new KeyValuePair<string, object?>($"param{index + 1}", me))
                .ToDictionary(me => me.Key, me => me.Value);

            using var responseMessage = await http.PostAsJsonAsync(url, body, REQUEST_JSON_OPTIONS);
            var response = await responseMessage.Content.ReadFromJsonAsync<WitResponse>();

            Assert.That(response, Is.Not.Null, $"Bridge REST call returned no response for {methodName}.");
            return response!;
        }

        public static string BuildGetUrl(string baseUrl, string methodName, params string[] parameters)
        {
            var url = $"{baseUrl.TrimEnd('/')}/{methodName}";
            if (parameters.Length == 0)
                return url;

            var query = string.Join("&", parameters.Select((me, index) => $"param{index + 1}={Uri.EscapeDataString(me)}"));
            return $"{url}?{query}";
        }

        public static async Task<BridgeLocalConnectionContext> ReadConnectionContextAsync(string path)
        {
            Assert.That(File.Exists(path), Is.True, $"Bridge local connection context file was not created: {path}");

            await using var stream = File.OpenRead(path);
            var context = await JsonSerializer.DeserializeAsync<BridgeLocalConnectionContext>(stream);
            Assert.That(context, Is.Not.Null, $"Bridge local connection context file could not be deserialized: {path}");
            return context!;
        }

        public static void DeleteTempDirectory(string path)
        {
            if (!Directory.Exists(path))
                return;

            try
            {
                Directory.Delete(path, true);
            }
            catch
            {
            }
        }

        #endregion
    }
}
