"""Regenerate python-security.json, the Python-made values the .NET compatibility tests verify.

Run with the backend's virtualenv from the repository root:
    apps/backend/.venv/Scripts/python.exe apps/server/tests/Weir.Core.Tests/Fixtures/make_python_security_fixture.py
"""
import json, os, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / "backend" / "src"))
os.environ.setdefault("WEIR_HOME", os.path.join(tempfile.gettempdir(), "weir-fixture-home"))
from itsdangerous import TimestampSigner
from argon2 import PasswordHasher
from argon2.low_level import hash_secret_raw, Type
from cryptography.fernet import Fernet

import weir.platform.auth.csrf as csrf
from weir.platform.auth.sessions import hash_session_token
from weir.platform.arr_library import arr_connection_crypto as crypto

FIXED = 1_790_000_000
TimestampSigner.get_timestamp = lambda self: FIXED

secret = "fixture-session-secret-0123456789abcdef"
raw_session = "fixture-raw-session-token_abcdefghijklmnopqrstu"
ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, salt_len=16)


class S:
    def __init__(self, credentials, session, previous=()):
        self.credentials_secret = credentials
        self.session_secret = session
        self.previous_credentials_secrets = tuple(previous)


out = {
    "generated_by": "apps/backend/.venv (argon2-cffi, itsdangerous, cryptography) via weir.platform.* helpers",
    "password": {
        "plain": "correct horse battery staple",
        "hash": ph.hash("correct horse battery staple"),
        "unicode_plain": "pässwörd-ünïcode-😀",
        "unicode_hash": ph.hash("pässwörd-ünïcode-😀"),
        "raw_vectors": [
            {"type": "id", "version": 19, "password": "password", "salt": "somesalt", "t": 2, "m": 64, "p": 2, "len": 40,
             "hex": hash_secret_raw(b"password", b"somesalt", time_cost=2, memory_cost=64, parallelism=2, hash_len=40, type=Type.ID).hex()},
            {"type": "i", "version": 19, "password": "password", "salt": "somesalt", "t": 2, "m": 64, "p": 2, "len": 100,
             "hex": hash_secret_raw(b"password", b"somesalt", time_cost=2, memory_cost=64, parallelism=2, hash_len=100, type=Type.I).hex()},
            {"type": "d", "version": 16, "password": "password", "salt": "somesalt", "t": 1, "m": 64, "p": 1, "len": 32,
             "hex": hash_secret_raw(b"password", b"somesalt", time_cost=1, memory_cost=64, parallelism=1, hash_len=32, type=Type.D, version=16).hex()},
            {"type": "id", "version": 19, "password": "pw", "salt": "saltsaltsaltsalt", "t": 1, "m": 256, "p": 3, "len": 64,
             "hex": hash_secret_raw(b"pw", b"saltsaltsaltsalt", time_cost=1, memory_cost=256, parallelism=3, hash_len=64, type=Type.ID).hex()},
        ],
    },
    "csrf": {
        "secret": secret,
        "timestamp": FIXED,
        "raw_session_token": raw_session,
        "anonymous": csrf.issue_csrf_token(secret),
        "session_bound": csrf.issue_csrf_token(secret, raw_session),
    },
    "session_token_hash": {"raw": raw_session, "sha256": hash_session_token(raw_session)},
    "credentials": {
        "plaintext": "arr-api-key-0123456789",
        "credentials_secret": "fixture-credentials-secret-0123456789",
        "previous_secret": "fixture-old-credentials-secret-012345",
        "session_secret": secret,
        "envelope_credentials": crypto.encrypt_arr_api_key(S("fixture-credentials-secret-0123456789", secret), "arr-api-key-0123456789"),
        "envelope_previous": crypto.encrypt_arr_api_key(S("fixture-old-credentials-secret-012345", secret), "arr-api-key-0123456789"),
        "envelope_session_legacy": crypto.encrypt_arr_api_key(S(None, secret), "arr-api-key-0123456789"),
        "raw_legacy_token": crypto._fernet_for_secret(secret).encrypt(b"legacy-raw-key").decode("ascii"),
    },
}
target = sys.argv[1] if len(sys.argv) > 1 else str(HERE / "python-security.json")
with open(target, "w", encoding="utf-8", newline="\n") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("wrote", target)
