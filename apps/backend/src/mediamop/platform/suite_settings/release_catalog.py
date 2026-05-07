"""Canonical GitHub release metadata helpers for MediaMop updates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

GH_OWNER = "jampat000"
GH_REPO = "MediaMop"
GH_REPO_SLUG = f"{GH_OWNER}/{GH_REPO}"
GH_RELEASES_LATEST_URL = f"https://api.github.com/repos/{GH_REPO_SLUG}/releases/latest"
GH_RELEASE_BY_TAG_URL_TEMPLATE = f"https://api.github.com/repos/{GH_REPO_SLUG}/releases/tags/{{tag}}"
WINDOWS_INSTALLER_ASSET_NAME = "MediaMopSetup.exe"
WINDOWS_INSTALLER_SHA256_ASSET_NAME = "MediaMopSetup.exe.sha256"


@dataclass(frozen=True, slots=True)
class GitHubReleaseAsset:
    name: str
    api_url: str
    browser_download_url: str
    size_bytes: int
    content_type: str | None


@dataclass(frozen=True, slots=True)
class GitHubReleaseRecord:
    tag_name: str
    version: str
    release_name: str | None
    html_url: str | None
    published_at: datetime | None
    draft: bool
    prerelease: bool
    assets: tuple[GitHubReleaseAsset, ...]

    def asset_named(self, name: str) -> GitHubReleaseAsset | None:
        wanted = name.strip().lower()
        for asset in self.assets:
            if asset.name.strip().lower() == wanted:
                return asset
        return None


def normalize_release_version(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    return text.removeprefix("v") or None


def tag_for_version(version: str) -> str:
    normalized = normalize_release_version(version)
    if not normalized:
        raise ValueError("Release version is missing.")
    return f"v{normalized}"


def parse_version_key(raw: str | None) -> tuple[int, ...] | None:
    normalized = normalize_release_version(raw)
    if not normalized:
        return None
    parts: list[int] = []
    for piece in normalized.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if digits == "":
            break
        parts.append(int(digits))
    return tuple(parts) if parts else None


def release_headers(user_agent_version: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"MediaMop/{user_agent_version}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _coerce_release_asset(payload: dict[str, Any]) -> GitHubReleaseAsset:
    name = str(payload.get("name") or "").strip()
    api_url = str(payload.get("url") or "").strip()
    if not name or not api_url:
        raise ValueError("Release asset metadata is incomplete.")
    return GitHubReleaseAsset(
        name=name,
        api_url=api_url,
        browser_download_url=str(payload.get("browser_download_url") or "").strip(),
        size_bytes=int(payload.get("size") or 0),
        content_type=(
            str(payload.get("content_type") or "").strip() or None
        ),
    )


def _coerce_release_payload(payload: dict[str, Any]) -> GitHubReleaseRecord:
    if not isinstance(payload, dict):
        raise ValueError("Release API returned an unexpected response.")
    tag_name = str(payload.get("tag_name") or "").strip()
    version = normalize_release_version(tag_name)
    if not version:
        raise ValueError("Release metadata is missing a valid tag name.")
    published_at_raw = payload.get("published_at")
    published_at = None
    if isinstance(published_at_raw, str) and published_at_raw.strip():
        published_at = datetime.fromisoformat(
            published_at_raw.strip().replace("Z", "+00:00")
        )
    assets_raw = payload.get("assets")
    assets: list[GitHubReleaseAsset] = []
    if isinstance(assets_raw, list):
        for item in assets_raw:
            if isinstance(item, dict):
                assets.append(_coerce_release_asset(item))
    return GitHubReleaseRecord(
        tag_name=tag_name,
        version=version,
        release_name=str(payload.get("name") or "").strip() or None,
        html_url=str(payload.get("html_url") or "").strip() or None,
        published_at=published_at,
        draft=bool(payload.get("draft")),
        prerelease=bool(payload.get("prerelease")),
        assets=tuple(assets),
    )


def fetch_latest_release_record(*, user_agent_version: str) -> GitHubReleaseRecord:
    with httpx.Client(
        timeout=5.0,
        headers=release_headers(user_agent_version),
        follow_redirects=True,
    ) as client:
        response = client.get(GH_RELEASES_LATEST_URL)
        response.raise_for_status()
        return _coerce_release_payload(response.json())


def fetch_release_record_by_version(
    version: str,
    *,
    user_agent_version: str,
) -> GitHubReleaseRecord:
    tag = tag_for_version(version)
    with httpx.Client(
        timeout=5.0,
        headers=release_headers(user_agent_version),
        follow_redirects=True,
    ) as client:
        response = client.get(GH_RELEASE_BY_TAG_URL_TEMPLATE.format(tag=tag))
        response.raise_for_status()
        record = _coerce_release_payload(response.json())
    if record.tag_name != tag:
        raise ValueError(
            f"Release tag mismatch for MediaMop update: expected {tag}, got {record.tag_name}."
        )
    if record.draft or record.prerelease:
        raise ValueError(
            f"MediaMop update {tag} is not a stable published release."
        )
    return record

