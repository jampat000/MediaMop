using Weir.Core.Json;
using Weir.Core.Security;
using Weir.Infrastructure.Auth;
using Weir.Infrastructure.Runtime;
using Weir.Infrastructure.Settings;

namespace Weir.Infrastructure.Tests.Platform;

/// <summary>
/// Values and rows made by .NET, checked by the Python backend itself (and the reverse where it needs a
/// running database). These run where <c>apps/backend/.venv</c> exists and are skipped elsewhere.
/// </summary>
public sealed class PythonCrossCheckTests
{
    private const string Secret = "cross-check-session-secret-0123456789";

    [PythonFact]
    public void A_dotnet_password_hash_verifies_in_python()
    {
        const string plain = "dotnet-made pässword 😀";
        var output = PythonBackend.Run(
            "import os\nfrom weir.platform.auth.password import verify_password\n" +
            "print(verify_password(os.environ['PLAIN'], os.environ['HASH']), verify_password('wrong', os.environ['HASH']))\n",
            new Dictionary<string, string> { ["PLAIN"] = plain, ["HASH"] = PasswordHasher.Hash(plain) });
        Assert.Equal("True False", output);
    }

    [PythonFact]
    public void Csrf_tokens_and_credential_envelopes_verify_across_both_implementations()
    {
        const string raw = "cross-check-raw-session-token";
        var anonymous = CsrfTokens.Issue(Secret, null, TimeProvider.System);
        var bound = CsrfTokens.Issue(Secret, raw, TimeProvider.System);
        var envelope = new CredentialCipher("cross-check-credentials-secret-012345", Secret, [], TimeProvider.System).Encrypt("arr-key-from-dotnet");
        var output = PythonBackend.Run(
            "import os\n" +
            "from weir.platform.auth.csrf import issue_csrf_token, verify_csrf_token\n" +
            "from weir.platform.arr_library.arr_connection_crypto import decrypt_arr_api_key, encrypt_arr_api_key\n" +
            "class S:\n    credentials_secret = 'cross-check-credentials-secret-012345'\n    session_secret = os.environ['SECRET']\n    previous_credentials_secrets = ()\n" +
            "e = os.environ\n" +
            "print(verify_csrf_token(e['SECRET'], e['ANON'], allow_anonymous=True), verify_csrf_token(e['SECRET'], e['BOUND'], raw_session_token=e['RAW']), verify_csrf_token(e['SECRET'], e['BOUND'], raw_session_token='other'))\n" +
            "print(decrypt_arr_api_key(S, e['ENVELOPE']))\n" +
            "print(issue_csrf_token(e['SECRET'], e['RAW']))\n" +
            "print(encrypt_arr_api_key(S, 'arr-key-from-python'))\n",
            new Dictionary<string, string> { ["SECRET"] = Secret, ["ANON"] = anonymous, ["BOUND"] = bound, ["RAW"] = raw, ["ENVELOPE"] = envelope });
        var lines = output.Split('\n').Select(line => line.Trim()).ToArray();
        Assert.Equal("True True False", lines[0]);
        Assert.Equal("arr-key-from-dotnet", lines[1]);
        Assert.True(CsrfTokens.Verify(Secret, lines[2], raw, allowAnonymous: false, TimeProvider.System));
        Assert.Equal("arr-key-from-python", new CredentialCipher("cross-check-credentials-secret-012345", Secret, [], TimeProvider.System).Decrypt(lines[3]));
    }

    [PythonFact]
    public async Task Sessions_created_by_either_server_authenticate_on_the_other()
    {
        using var fixture = new StoreFixture(("WEIR_SESSION_SECRET", Secret));
        fixture.Clock.Set(DateTimeOffset.UtcNow);
        const string password = "cross-check-password-1";
        var userId = await fixture.WithUnitOfWork(uow => AuthStore.InsertUserAsync(uow, "alice", PasswordHasher.Hash(password), "admin", true));
        var (_, dotnetRaw) = await fixture.WithUnitOfWork(uow =>
            fixture.Auth.CreateSessionAsync(uow, new Core.Auth.UserRecord(userId, "alice", string.Empty, "admin", true), false, "Chrome on Windows"));

        var output = PythonBackend.Run(
            "import os\n" +
            "from weir.core.config import WeirSettings\n" +
            "from weir.core.db import create_db_engine, create_session_factory\n" +
            "from weir.platform.auth import service\n" +
            "s = WeirSettings.load()\n" +
            "fac = create_session_factory(create_db_engine(s))\n" +
            "with fac() as db:\n" +
            "    pair = service.load_valid_session_for_request(db, os.environ['RAW'], s)\n" +
            "    print(pair[1].username if pair else 'NONE', pair[0].client_label if pair else '')\n" +
            "    user = service.authenticate_user(db, 'ALICE', os.environ['PASSWORD'])\n" +
            "    row, raw = service.create_user_session(db, user, settings=s, trusted_device=True, client_label='Firefox on Linux')\n" +
            "    db.commit()\n" +
            "    print(raw)\n",
            new Dictionary<string, string>
            {
                ["WEIR_HOME"] = fixture.Home.Path,
                ["WEIR_SESSION_SECRET"] = Secret,
                ["RAW"] = dotnetRaw,
                ["PASSWORD"] = password,
            });
        var lines = output.Split('\n').Select(line => line.Trim()).ToArray();
        Assert.Equal("alice Chrome on Windows", lines[0]);

        var fromPython = await fixture.WithUnitOfWork(uow => fixture.Auth.LoadValidSessionAsync(uow, lines[1]));
        Assert.NotNull(fromPython);
        Assert.Equal("alice", fromPython.User.Username);
        Assert.True(fromPython.Session.IsTrustedDevice);
        Assert.Equal("Firefox on Linux", fromPython.Session.ClientLabel);
        Assert.Matches("^[0-9a-f]{8}-[0-9a-f]{4}-", fromPython.Session.PublicId);
    }

    [PythonFact]
    public async Task A_python_bundle_imports_on_dotnet_and_the_dotnet_export_imports_on_python()
    {
        using var fixture = new StoreFixture(("WEIR_SESSION_SECRET", Secret));
        var pythonBundle = (PyDict)PyJsonParser.Parse(await File.ReadAllTextAsync(Path.Join(AppContext.BaseDirectory, "Fixtures", "python-bundle-v4.json")));
        await fixture.WithUnitOfWork(async uow =>
        {
            await ConfigurationBundleStore.ApplyAsync(uow, pythonBundle, new IanaTimeZoneResolver());
            return 0;
        });
        var exported = await fixture.WithUnitOfWork(ConfigurationBundleStore.BuildAsync);
        Assert.Equal(StripTimestamps(pythonBundle), StripTimestamps(exported));

        var bundlePath = fixture.Home.Join("dotnet-bundle.json");
        await File.WriteAllTextAsync(bundlePath, PyJsonWriter.Dumps(exported, PyJsonFormat.IndentedSorted));
        using var pythonHome = new StoreFixture(("WEIR_SESSION_SECRET", Secret));
        var output = PythonBackend.Run(
            "import json, os\n" +
            "import weir.api.factory  # registers every ORM model\n" +
            "from weir.core.config import WeirSettings\n" +
            "from weir.core.db import create_db_engine, create_session_factory\n" +
            "from weir.platform.configuration_bundle.service import apply_configuration_bundle, build_configuration_bundle\n" +
            "s = WeirSettings.load()\n" +
            "fac = create_session_factory(create_db_engine(s))\n" +
            "bundle = json.load(open(os.environ['BUNDLE'], encoding='utf-8'))\n" +
            "with fac() as db:\n" +
            "    apply_configuration_bundle(db, bundle)\n" +
            "    db.commit()\n" +
            "with fac() as db:\n" +
            "    print(json.dumps(build_configuration_bundle(db), sort_keys=True))\n",
            new Dictionary<string, string> { ["WEIR_HOME"] = pythonHome.Home.Path, ["WEIR_SESSION_SECRET"] = Secret, ["BUNDLE"] = bundlePath });
        var reimported = (PyDict)PyJsonParser.Parse(output.Split('\n')[^1]);
        Assert.Equal("Exported By Python", ((PyStr)((PyDict)reimported["suite_settings"])["product_display_name"]).Value);
        Assert.Equal(StripTimestamps(exported), StripTimestamps(reimported));
    }

    /// <summary>
    /// The bundle with every timestamp removed. Python writes naive UTC timestamps as if they were local time
    /// (<c>astimezone(UTC)</c> on a naive value), so they shift by the machine's offset on each round trip; the
    /// .NET port keeps that behaviour and the comparison leaves them out.
    /// </summary>
    private static string StripTimestamps(PyDict bundle)
    {
        static PyJson Strip(PyJson value) => value switch
        {
            PyDict dict => dict.Items.Where(pair => !pair.Key.EndsWith("_at", StringComparison.Ordinal) && !pair.Key.StartsWith("created_", StringComparison.Ordinal) && !pair.Key.StartsWith("modified_", StringComparison.Ordinal))
                .Aggregate(new PyDict(), (acc, pair) => acc.Set(pair.Key, Strip(pair.Value))),
            PyList list => new PyList(list.Items.Select(Strip)),
            _ => value,
        };
        return PyJsonWriter.Dumps(Strip(bundle), PyJsonFormat.IndentedSorted);
    }
}
