"""Safe filesystem/database reconciliation checks and repairs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.refiner_library_service import list_libraries
from mediamop.platform.file_lifecycle.mutations import safe_unlink_under_roots

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


def _configured_refiner_work_roots(session: Session) -> list[Path]:
    """Every library's work root. Reads the libraries now the singletons are gone (#363),
    which also means a third library's work folder is no longer skipped."""

    roots: list[Path] = []
    for raw in (library.work_folder for library in list_libraries(session)):
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


def _scan_refiner_paths(session: Session) -> list[ReconciliationIssue]:
    libraries = list_libraries(session)
    if not libraries:
        return []

    issues: list[ReconciliationIssue] = []
    # Every library, not two fixed scopes: a third library's unreachable folder used to
    # go unreported entirely because the singleton had nowhere to put it.
    configured_folders = [
        ("refiner", f"{library.name} {role} folder", raw, library.id)
        for library in libraries
        for role, raw in (
            ("watched", library.watched_folder),
            ("output", library.output_folder),
            ("work", library.work_folder),
        )
    ]
    for module, label, raw, library_id in configured_folders:
        if raw and str(raw).strip() and not _path_exists(str(raw)):
            issues.append(
                ReconciliationIssue(
                    kind="configured_folder_missing",
                    module=module,
                    severity="warning",
                    message=f"{label} is configured but is not currently reachable on disk.",
                    path=str(raw),
                    db_table="refiner_libraries",
                    db_id=library_id,
                )
            )

    for root in _configured_refiner_work_roots(session):
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
    issues = _scan_refiner_paths(session)
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
    if action == "remove_refiner_temp_artifact":
        if not confirm:
            raise ValueError("confirm=true is required before removing a Refiner temp artifact.")
        if not path or not path.strip():
            raise ValueError("path is required for this repair action.")
        roots = _configured_refiner_work_roots(session)
        target = Path(path)
        if not _is_temp_artifact(target):
            raise ValueError("Refusing to remove a file that does not look like a temp artifact.")
        removed = safe_unlink_under_roots(target, allowed_roots=roots)
        return {
            "applied": removed,
            "message": "Removed the Refiner temp artifact." if removed else "Temp artifact is already gone.",
        }

    raise ValueError(f"Unknown reconciliation repair action: {action}")
