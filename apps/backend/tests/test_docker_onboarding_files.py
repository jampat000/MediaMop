from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_compose_documents_session_secret_generation() -> None:
    compose = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "MEDIAMOP_SESSION_SECRET" in compose
    assert "openssl rand -hex 32" in compose
    assert "session.secret" in compose


def test_docker_env_example_documents_required_and_recommended_values() -> None:
    example = (REPO_ROOT / "docker" / ".env.example").read_text(encoding="utf-8")

    assert "MEDIAMOP_SESSION_SECRET" in example
    assert "MEDIAMOP_CREDENTIALS_SECRET" in example
    assert "openssl rand -hex 32" in example
    assert "MEDIAMOP_HOME" in example


def test_docker_entrypoint_generates_persistent_session_secret() -> None:
    entrypoint = (REPO_ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")

    assert "generate_secret()" in entrypoint
    assert "session.secret" in entrypoint
    assert "export MEDIAMOP_SESSION_SECRET" in entrypoint
    assert "must be at least 32 characters" in entrypoint


def test_dockerfile_runs_as_non_root_user() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "useradd --system --uid 1000" in dockerfile
    assert "USER mediamop" in dockerfile
