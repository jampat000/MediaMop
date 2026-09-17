using System.Text;
using System.Text.Json;
using Weir.Core.Security;

namespace Weir.Core.Tests.Security;

/// <summary>
/// Values made by the Python backend (Fixtures/python-security.json) must verify here, and values made
/// here must match what Python makes, so a database and a browser survive switching servers.
/// </summary>
public sealed class PythonSecurityCompatibilityTests
{
    private static readonly JsonElement Fixture = JsonDocument.Parse(
        File.ReadAllText(Path.Join(AppContext.BaseDirectory, "Fixtures", "python-security.json"))).RootElement;

    [Fact]
    public void Argon2id_hashes_made_by_argon2_cffi_verify()
    {
        var password = Fixture.GetProperty("password");
        Assert.Equal(PasswordVerification.Match, PasswordHasher.Verify(password.GetProperty("plain").GetString()!, password.GetProperty("hash").GetString()!));
        Assert.Equal(PasswordVerification.Match, PasswordHasher.Verify(password.GetProperty("unicode_plain").GetString()!, password.GetProperty("unicode_hash").GetString()!));
        Assert.Equal(PasswordVerification.Mismatch, PasswordHasher.Verify("wrong", password.GetProperty("hash").GetString()!));
    }

    [Fact]
    public void Raw_argon2_output_matches_the_reference_library_for_every_variant()
    {
        foreach (var vector in Fixture.GetProperty("password").GetProperty("raw_vectors").EnumerateArray())
        {
            var type = vector.GetProperty("type").GetString() switch
            {
                "id" => Argon2Type.Argon2id,
                "i" => Argon2Type.Argon2i,
                _ => Argon2Type.Argon2d,
            };
            var tag = Argon2.Hash(
                type,
                vector.GetProperty("version").GetInt32(),
                Encoding.UTF8.GetBytes(vector.GetProperty("password").GetString()!),
                Encoding.UTF8.GetBytes(vector.GetProperty("salt").GetString()!),
                [],
                [],
                vector.GetProperty("t").GetInt32(),
                vector.GetProperty("m").GetInt32(),
                vector.GetProperty("p").GetInt32(),
                vector.GetProperty("len").GetInt32());
            Assert.Equal(vector.GetProperty("hex").GetString(), Convert.ToHexStringLower(tag));
        }
    }

    [Fact]
    public void Argon2id_matches_the_rfc_9106_test_vector()
    {
        var tag = Argon2.Hash(
            Argon2Type.Argon2id, Argon2.Version13,
            Enumerable.Repeat((byte)1, 32).ToArray(), Enumerable.Repeat((byte)2, 16).ToArray(),
            Enumerable.Repeat((byte)3, 8).ToArray(), Enumerable.Repeat((byte)4, 12).ToArray(),
            iterations: 3, memoryKib: 32, parallelism: 4, hashLength: 32);
        Assert.Equal("0d640df58d78766c08c037a34a8b53c9d01ef0452d75b65eb52520e96b01e659", Convert.ToHexStringLower(tag));
    }

    [Fact]
    public void New_hashes_use_the_python_parameters_and_phc_format()
    {
        var hash = PasswordHasher.Hash("correct horse battery staple");
        Assert.Matches(@"^\$argon2id\$v=19\$m=65536,t=3,p=1\$[A-Za-z0-9+/]{22}\$[A-Za-z0-9+/]{43}$", hash);
        Assert.Equal(PasswordVerification.Match, PasswordHasher.Verify("correct horse battery staple", hash));
    }

    [Theory]
    [InlineData("not-a-valid-phc-string")]
    [InlineData("$argon2id$v=19$m=65536,t=3,p=1$bad")]
    [InlineData("$argon2id$v=19$m=65536,t=3$c2FsdHNhbHQ$aGFzaGhhc2g")]
    [InlineData("$argon2id$v=19$m=65536,t=3,p=1$c2FsdHNhbHQ=$aGFzaGhhc2g")]
    public void Unreadable_stored_hashes_are_reported_not_thrown(string stored) =>
        Assert.Equal(PasswordVerification.InvalidHash, PasswordHasher.Verify("secret", stored));

    [Fact]
    public void An_empty_stored_hash_is_a_mismatch() => Assert.Equal(PasswordVerification.Mismatch, PasswordHasher.Verify("x", string.Empty));

    [Fact]
    public void Csrf_tokens_issued_by_python_verify_and_dotnet_issues_identical_tokens()
    {
        var csrf = Fixture.GetProperty("csrf");
        var secret = csrf.GetProperty("secret").GetString()!;
        var raw = csrf.GetProperty("raw_session_token").GetString()!;
        var clock = new FixedClock(DateTimeOffset.FromUnixTimeSeconds(csrf.GetProperty("timestamp").GetInt64()));

        var anonymous = csrf.GetProperty("anonymous").GetString()!;
        var bound = csrf.GetProperty("session_bound").GetString()!;
        Assert.True(CsrfTokens.Verify(secret, anonymous, null, allowAnonymous: true, clock));
        Assert.True(CsrfTokens.Verify(secret, bound, raw, allowAnonymous: false, clock));
        Assert.False(CsrfTokens.Verify(secret, bound, raw + "x", allowAnonymous: false, clock));
        Assert.False(CsrfTokens.Verify(secret, anonymous, raw, allowAnonymous: false, clock));

        Assert.Equal(anonymous, CsrfTokens.Issue(secret, null, clock));
        Assert.Equal(bound, CsrfTokens.Issue(secret, raw, clock));
    }

    [Fact]
    public void Csrf_tokens_expire_after_an_hour_and_are_refused_from_the_future()
    {
        var csrf = Fixture.GetProperty("csrf");
        var secret = csrf.GetProperty("secret").GetString()!;
        var issuedAt = DateTimeOffset.FromUnixTimeSeconds(csrf.GetProperty("timestamp").GetInt64());
        var token = csrf.GetProperty("anonymous").GetString()!;

        Assert.True(CsrfTokens.Verify(secret, token, null, true, new FixedClock(issuedAt.AddSeconds(3600))));
        Assert.False(CsrfTokens.Verify(secret, token, null, true, new FixedClock(issuedAt.AddSeconds(3601))));
        Assert.False(CsrfTokens.Verify(secret, token, null, true, new FixedClock(issuedAt.AddSeconds(-1))));
        Assert.False(CsrfTokens.Verify("another-secret", token, null, true, new FixedClock(issuedAt)));
        Assert.False(CsrfTokens.Verify(secret, "tampered", null, true, new FixedClock(issuedAt)));
        Assert.False(CsrfTokens.Verify(secret, token[..^1] + (token[^1] == 'A' ? 'B' : 'A'), null, true, new FixedClock(issuedAt)));
    }

    [Fact]
    public void Session_token_hashes_match_python()
    {
        var hash = Fixture.GetProperty("session_token_hash");
        Assert.Equal(hash.GetProperty("sha256").GetString(), SessionTokens.Hash(hash.GetProperty("raw").GetString()!));
        Assert.Matches("^[A-Za-z0-9_-]{43}$", SessionTokens.Generate());
    }

    [Fact]
    public void Credential_envelopes_encrypted_by_python_decrypt()
    {
        var credentials = Fixture.GetProperty("credentials");
        var plaintext = credentials.GetProperty("plaintext").GetString()!;
        var current = credentials.GetProperty("credentials_secret").GetString()!;
        var previous = credentials.GetProperty("previous_secret").GetString()!;
        var session = credentials.GetProperty("session_secret").GetString()!;

        var cipher = new CredentialCipher(current, session, [previous], TimeProvider.System);
        Assert.Equal(plaintext, cipher.Decrypt(credentials.GetProperty("envelope_credentials").GetString()));
        Assert.Equal(plaintext, cipher.Decrypt(credentials.GetProperty("envelope_previous").GetString()));
        Assert.Equal(plaintext, cipher.Decrypt(credentials.GetProperty("envelope_session_legacy").GetString()));
        Assert.Equal("legacy-raw-key", cipher.Decrypt(credentials.GetProperty("raw_legacy_token").GetString()));

        var withoutPrevious = new CredentialCipher(current, "rotated-session-secret", [], TimeProvider.System);
        Assert.Null(withoutPrevious.Decrypt(credentials.GetProperty("envelope_previous").GetString()));
        Assert.Null(withoutPrevious.Decrypt(credentials.GetProperty("envelope_session_legacy").GetString()));
        Assert.Equal(plaintext, withoutPrevious.Decrypt(credentials.GetProperty("envelope_credentials").GetString()));
    }

    [Fact]
    public void Credential_encryption_uses_the_python_envelope_and_rewraps_legacy_values()
    {
        var legacy = new CredentialCipher(null, "legacy-session-secret", [], TimeProvider.System);
        var legacyCiphertext = legacy.Encrypt("  arr-key  ");
        using (var envelope = JsonDocument.Parse(legacyCiphertext))
        {
            Assert.Equal(["version", "key_id", "token"], envelope.RootElement.EnumerateObject().Select(p => p.Name));
            Assert.Equal(2, envelope.RootElement.GetProperty("version").GetInt32());
            Assert.Equal("session-legacy:v1", envelope.RootElement.GetProperty("key_id").GetString());
        }

        Assert.DoesNotContain(' ', legacyCiphertext);
        var migrated = new CredentialCipher("new-credentials-secret", "legacy-session-secret", [], TimeProvider.System);
        var rewrapped = migrated.Rewrap(legacyCiphertext);
        var rotated = new CredentialCipher("new-credentials-secret", "rotated-session-secret", [], TimeProvider.System);
        Assert.NotNull(rewrapped);
        Assert.Equal("arr-key", rotated.Decrypt(rewrapped));
        Assert.Throws<Core.Json.PyValueErrorException>(() => new CredentialCipher(null, null, [], TimeProvider.System).Encrypt("x"));
    }

    private sealed class FixedClock(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }
}
