"""Static contract for Pruner operator-facing workflow language."""

from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_pruner_operator_sources() -> str:
    root = _repo_root()
    paths = [
        *(root / "apps" / "web" / "src" / "pages" / "pruner").glob("*.tsx"),
        *(root / "apps" / "backend" / "src" / "mediamop" / "modules" / "pruner").glob("*.py"),
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_pruner_operator_copy_uses_preview_apply_not_dry_run() -> None:
    text = _read_pruner_operator_sources().lower()

    assert "dry run" not in text
    assert "dry-run" not in text
    assert "dry_run" not in text
    assert "preview" in text
    assert "apply" in text


def test_pruner_operator_copy_avoids_vague_this_tab_language() -> None:
    text = _read_pruner_operator_sources().lower()

    assert "this tab" not in text
