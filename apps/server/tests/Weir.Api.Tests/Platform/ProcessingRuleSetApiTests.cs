using System.Net;

namespace Weir.Api.Tests.Platform;

/// <summary>
/// HTTP-level round trip for issues #495/#497/#498's new rule-set fields
/// (<c>POST</c>/<c>PUT /api/v1/processing/rule-sets</c>) and their validation: an unknown track name
/// template placeholder (400, matching <c>TrackNaming.ValidateAll</c>), a negative subtitle cap and an
/// unknown enum value (422, the same field-validation path every other rule-set enum/numeric field uses).
/// </summary>
public sealed class ProcessingRuleSetApiTests
{
    private static object FullRuleSetBody(string csrfToken, string name) => new
    {
        csrf_token = csrfToken,
        name,
        remove_hearing_impaired_subs = true,
        audio_keep_mode = "per_language",
        subtitle_max_per_language = 2,
        subtitle_quality_strategy = "accessibility",
        standardize_track_names = true,
        track_name_template = "{language} {channels} {codec}",
        track_name_overrides = new
        {
            forced = "{language} (Forced)",
            hearing_impaired = "{language} (SDH)",
            commentary = "{language} (Commentary)",
            audio_description = "{language} (AD)",
        },
        clear_video_track_names = true,
        remove_chapters = true,
    };

    private static void AssertFullRuleSetFields(System.Text.Json.Nodes.JsonNode body)
    {
        Assert.True(body["remove_hearing_impaired_subs"]!.GetValue<bool>());
        Assert.Equal("per_language", body["audio_keep_mode"]!.GetValue<string>());
        Assert.Equal(2, body["subtitle_max_per_language"]!.GetValue<int>());
        Assert.Equal("accessibility", body["subtitle_quality_strategy"]!.GetValue<string>());
        Assert.True(body["standardize_track_names"]!.GetValue<bool>());
        Assert.Equal("{language} {channels} {codec}", body["track_name_template"]!.GetValue<string>());
        var overrides = body["track_name_overrides"]!;
        Assert.Equal("{language} (Forced)", overrides["forced"]!.GetValue<string>());
        Assert.Equal("{language} (SDH)", overrides["hearing_impaired"]!.GetValue<string>());
        Assert.Equal("{language} (Commentary)", overrides["commentary"]!.GetValue<string>());
        Assert.Equal("{language} (AD)", overrides["audio_description"]!.GetValue<string>());
        Assert.True(body["clear_video_track_names"]!.GetValue<bool>());
        Assert.True(body["remove_chapters"]!.GetValue<bool>());
    }

    [Fact]
    public async Task Creating_a_rule_set_round_trips_every_new_field()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();

        using var response = await client.PostAsync(
            "/api/v1/processing/rule-sets",
            FullRuleSetBody(await client.CsrfAsync(), "New profile " + Guid.NewGuid().ToString("N")));

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        AssertFullRuleSetFields(await ApiTestClient.Json(response));
    }

    [Fact]
    public async Task A_rule_set_defaults_to_the_engines_shipped_defaults_for_every_new_field()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();

        using var response = await client.PostAsync(
            "/api/v1/processing/rule-sets",
            new { csrf_token = await client.CsrfAsync(), name = "Defaults " + Guid.NewGuid().ToString("N") });

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var body = await ApiTestClient.Json(response);
        Assert.False(body["remove_hearing_impaired_subs"]!.GetValue<bool>());
        Assert.Equal("single", body["audio_keep_mode"]!.GetValue<string>());
        Assert.Equal(0, body["subtitle_max_per_language"]!.GetValue<int>());
        Assert.Equal("text_first", body["subtitle_quality_strategy"]!.GetValue<string>());
        Assert.False(body["standardize_track_names"]!.GetValue<bool>());
        Assert.Equal("{language}{variant} {channels} {codec}", body["track_name_template"]!.GetValue<string>());
        Assert.False(body["clear_video_track_names"]!.GetValue<bool>());
        Assert.False(body["remove_chapters"]!.GetValue<bool>());
    }

    [Fact]
    public async Task Updating_a_rule_set_round_trips_every_new_field()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();
        using var created = await client.PostAsync(
            "/api/v1/processing/rule-sets",
            new { csrf_token = await client.CsrfAsync(), name = "To update " + Guid.NewGuid().ToString("N") });
        var id = (await ApiTestClient.Json(created))!["id"]!.GetValue<long>();

        using var updated = await client.PutAsync(
            $"/api/v1/processing/rule-sets/{id}",
            FullRuleSetBody(await client.CsrfAsync(), "Updated " + Guid.NewGuid().ToString("N")));

        Assert.Equal(HttpStatusCode.OK, updated.StatusCode);
        AssertFullRuleSetFields(await ApiTestClient.Json(updated));

        using var listResponse = await client.GetAsync("/api/v1/processing/rule-sets");
        var list = (await ApiTestClient.Json(listResponse))!.AsArray();
        var reloaded = list.Single(row => row!["id"]!.GetValue<long>() == id);
        AssertFullRuleSetFields(reloaded!);
    }

    [Fact]
    public async Task An_unknown_track_name_template_placeholder_is_refused_with_400()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();

        using var response = await client.PostAsync(
            "/api/v1/processing/rule-sets",
            new
            {
                csrf_token = await client.CsrfAsync(),
                name = "Bad template " + Guid.NewGuid().ToString("N"),
                track_name_template = "{language} {bogus}",
            });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Contains("bogus", await ApiTestClient.Detail(response), StringComparison.Ordinal);
    }

    [Fact]
    public async Task An_unknown_placeholder_in_a_track_name_override_is_refused_with_400()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();

        using var response = await client.PostAsync(
            "/api/v1/processing/rule-sets",
            new
            {
                csrf_token = await client.CsrfAsync(),
                name = "Bad override " + Guid.NewGuid().ToString("N"),
                track_name_overrides = new { forced = "{bogus}" },
            });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Contains("bogus", await ApiTestClient.Detail(response), StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_negative_subtitle_cap_is_refused_with_422()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();

        using var response = await client.PostAsync(
            "/api/v1/processing/rule-sets",
            new
            {
                csrf_token = await client.CsrfAsync(),
                name = "Negative cap " + Guid.NewGuid().ToString("N"),
                subtitle_max_per_language = -1,
            });

        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
    }

    [Theory]
    [InlineData("audio_keep_mode", "bogus")]
    [InlineData("subtitle_quality_strategy", "bogus")]
    public async Task An_unknown_enum_value_is_refused_with_422(string field, string value)
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();
        var body = new Dictionary<string, object?>
        {
            ["csrf_token"] = await client.CsrfAsync(),
            ["name"] = "Unknown enum " + Guid.NewGuid().ToString("N"),
            [field] = value,
        };

        using var response = await client.PostAsync("/api/v1/processing/rule-sets", body);

        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
    }

    [Fact]
    public async Task An_unknown_field_in_track_name_overrides_is_refused_with_422()
    {
        await using var server = await ApiTestClient.StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();

        using var response = await client.PostAsync(
            "/api/v1/processing/rule-sets",
            new
            {
                csrf_token = await client.CsrfAsync(),
                name = "Extra override field " + Guid.NewGuid().ToString("N"),
                track_name_overrides = new { forced = "{language}", bogus_flag = "x" },
            });

        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
    }
}
