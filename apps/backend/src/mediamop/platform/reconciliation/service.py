"""Safe filesystem/database reconciliation checks and repairs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow
from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState
from mediamop.platform.file_lifecycle.mutations import safe_unlink

TEMP_ARTIFACT_SUFFIXES = (".partial", ".part", ".tmp", ".link")
MAX_ISSUES_PER_CATEGORY = 200


@dataclass(frozen=True)
class ReconciliationIssue:
    kind: str
    module: str
    severity: str
    message: str
    path: str | None = None
    db_table: str | None = None
    db_id: int | None = None
    repair_action: str | None = None
    requires_confirmation: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "module": self.module,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "db_table": self.db_table,
            "db_id": self.db_id,
            "repair_action": self.repair_action,
            "requires_confirmation": self.requires_confirmation,
        }


def _path_exists(raw: str | None) -> bool:
    if not raw or not raw.strip():
        return False
    try:
        return Path(raw).exists()  # codeql[py/path-injection] read-only reachability check for stored paths.
    except OSError:
        return False


def _configured_refiner_work_roots(row: RefinerPathSettingsRow | None) -> list[Path]:
    if row is None:
        return []
    roots: list[Path] = []
    for raw in (row.refiner_work_folder, row.refiner_tv_work_folder):
        if not raw or not str(raw).strip():
            continue
        try:
            root = Path(str(raw)).resolve()
        except OSError:
            continue
        if root.is_dir():
            roots.append(root)
    return roots


def _is_temp_artifact(path: Path) -> bool:
    name = path.name.lower()
    return name.startswith(".") or name.endswith(TEMP_ARTIFACT_SUFFIXES)


def _is_under_root(path: Path, root: Path) -> bool:
    try:
        # codeql[py/path-injection] this is a containment check, not a file mutation.
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
    except OSError:
        return False


def _scan_subber_state(session: Session) -> list[ReconciliationIssue]:
    issues: list[ReconciliationIssue] = []
    rows = list(session.scalars(select(SubberSubtitleState).order_by(SubberSubtitleState.id.asc())))
    for row in rows:
        if len(issues) >= MAX_ISSUES_PER_CATEGORY:
            break
        if not _path_exists(row.file_path):
            issues.append(
                ReconciliationIssue(
                    kind="db_media_file_missing",
                    module="subber",
                    severity="warning",
                    message="Subber has a media row for a file that is no longer on disk.",
                    path=row.file_path,
                    db_table="subber_subtitle_state",
                    db_id=int(row.id),
                    repair_action="remove_subber_state_row",
                    requires_confirmation=True,
                )
            )
            continue
        if row.subtitle_path and not _path_exists(row.subtitle_path):
            issues.append(
                ReconciliationIssue(
                    kind="db_subtitle_file_missing",
                    module="subber",
                    severity="warning",
                    message="Subber points at a subtitle file that is no longer on disk.",
                    path=row.subtitle_path,
                    db_table="subber_subtitle_state",
                    db_id=int(row.id),
                    repair_action="clear_missing_subtitle_reference",
                    requires_confirmation=False,
                )
            )
    return issues


def _scan_refiner_paths(session: Session) -> list[ReconciliationIssue]:
    row = session.get(RefinerPathSettingsRow, 1)
    if row is None:
        return []

    issues: list[ReconciliationIssue] = []
    configured_folders = (
        ("refiner", "Movies watched folder", row.refiner_watched_folder),
        ("refiner", "Movies output folder", row.refiner_output_folder),
        ("refiner", "Movies work folder", row.refiner_work_folder),
        ("refiner", "TV watched folder", row.refiner_tv_watched_folder),
        ("refiner", "TV output folder", row.refiner_tv_output_folder),
        ("refiner", "TV work folder", row.refiner_tv_work_folder),
    )
    for module, label, raw in configured_folders:
        if raw and str(raw).strip() and not _path_exists(str(raw)):
            issues.append(
                ReconciliationIssue(
                    kind="configured_folder_missing",
                    module=module,
                    severity="warning",
                    message=f"{label} is configured but is not currently reachable on disk.",
                    path=str(raw),
                    db_table="refiner_path_settings",
                    db_id=1,
                )
            )

    for root in _configured_refiner_work_roots(row):
        for path in root.rglob("*"):
            if len(issues) >= MAX_ISSUES_PER_CATEGORY:
                return issues
            if path.is_file() and _is_temp_artifact(path):
                issues.append(
                    ReconciliationIssue(
                        kind="partial_temp_artifact",
                        module="refiner",
                        severity="info",
                        message="Refiner work folder contains a temporary artifact from an interrupted operation.",
                        path=str(path),
                        repair_action="remove_refiner_temp_artifact",
                        requires_confirmation=True,
                    )
                )
    return issues


def build_reconciliation_report(session: Session) -> dict[str, Any]:
    issues = [*_scan_subber_state(session), *_scan_refiner_paths(session)]
    return {
        "ok": len(issues) == 0,
        "issue_count": len(issues),
        "issues": [issue.as_dict() for issue in issues],
        "repair_actions": sorted({issue.repair_action for issue in issues if issue.repair_action}),
    }


def repair_reconciliation_issue(
    session: Session,
    *,
    action: str,
    db_id: int | None = None,
    path: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    if action == "clear_missing_subtitle_reference":
        if db_id is None:
            raise ValueError("db_id is required for this repair action.")
        row = session.get(SubberSubtitleState, int(db_id))
        if row is None:
            return {"applied": False, "message": "Subtitle tracking row is already gone."}
        if row.subtitle_path and _path_exists(row.subtitle_path):
            return {"applied": False, "message": "Subtitle file exists now; no repair was applied."}
        row.subtitle_path = None
        row.status = "missing"
        session.flush()
        return {"applied": True, "message": "Cleared the missing subtitle reference and marked it missing again."}

    if action == "remove_subber_state_row":
        if not confirm:
            raise ValueError("confirm=true is required before removing a Subber tracking row.")
        if db_id is None:
            raise ValueError("db_id is required for this repair action.")
        row = session.get(SubberSubtitleState, int(db_id))
        if row is None:
            return {"applied": False, "message": "Subber tracking row is already gone."}
        if _path_exists(row.file_path):
            return {"applied": False, "message": "Media file exists now; no repair was applied."}
        session.delete(row)
        session.flush()
        return {"applied": True, "message": "Removed the stale Subber tracking row."}

    if action == "remove_refiner_temp_artifact":
        if not confirm:
            raise ValueError("confirm=true is required before removing a Refiner temp artifact.")
        if not path or not path.strip():
            raise ValueError("path is required for this repair action.")
        row = session.get(RefinerPathSettingsRow, 1)
        roots = _configured_refiner_work_roots(row)
        # codeql[py/path-injection] constrained to configured Refiner work roots before deletion.
        target = Path(path).resolve()
        if not any(_is_under_root(target, root) for root in roots):
            raise ValueError("Refusing to remove a file outside configured Refiner work folders.")
        if not _is_temp_artifact(target):
            raise ValueError("Refusing to remove a file that does not look like a temp artifact.")
        removed = safe_unlink(target)
        return {
            "applied": removed,
            "message": "Removed the Refiner temp artifact." if removed else "Temp artifact is already gone.",
        }

    raise ValueError(f"Unknown reconciliation repair action: {action}")
