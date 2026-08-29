"""Build and apply JSON configuration bundles (suite + module settings rows)."""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from typing import Any, TypeVar, cast

from sqlalchemy import DateTime, delete, inspect, select
from sqlalchemy.orm import Mapper, Session

from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings
from mediamop.modules.pruner.pruner_server_instance_model import PrunerServerInstance
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow, RefinerRuleSetRow
from mediamop.modules.refiner.refiner_library_service import resolve_library
from mediamop.modules.refiner.refiner_operator_settings_model import RefinerOperatorSettingsRow
from mediamop.platform.arr_library.arr_operator_settings_model import ArrLibraryOperatorSettingsRow
from mediamop.platform.suite_settings.model import SuiteSettingsRow
from mediamop.platform.suite_settings.service import apply_suite_settings_put, ensure_suite_settings_row

BUNDLE_FORMAT_VERSION = 4
#: Bundles this reader still accepts. Version 3 carried the Refiner singleton settings
#: tables, which are gone (#363). A backup taken the day before an upgrade must still be
#: restorable, so a v3 bundle is translated onto the libraries rather than refused — the
#: same mapping migration 0011 applied when it seeded them.
SUPPORTED_BUNDLE_FORMAT_VERSIONS = (3, 4)

T = TypeVar("T")


def _serialize_cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value


def orm_row_to_dict(obj: Any) -> dict[str, Any]:
    mapper = cast(Mapper[Any], inspect(obj.__class__, raiseerr=True))
    out: dict[str, Any] = {}
    for col in mapper.columns:
        key = col.key
        out[key] = _serialize_cell(getattr(obj, key))
    return out


def _parse_datetime(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        s = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    return None


def dict_to_model_kwargs(model_cls: type[T], data: dict[str, Any]) -> dict[str, Any]:
    mapper = cast(Mapper[Any], inspect(model_cls, raiseerr=True))
    cols = {c.key: c for c in mapper.columns}
    out: dict[str, Any] = {}
    for key, raw in data.items():
        if key not in cols:
            continue
        col = cols[key]
        if raw is None:
            out[key] = None
            continue
        col_type = col.type
        if isinstance(col_type, DateTime) or isinstance(getattr(col_type, "impl", None), DateTime):
            out[key] = _parse_datetime(raw)
        else:
            out[key] = raw
    return out


def _sanitize_pruner_scope_export(d: dict[str, Any]) -> dict[str, Any]:
    """Avoid dangling FKs to pruner_preview_runs when restoring on a fresh DB."""
    x = dict(d)
    x["last_preview_run_id"] = None
    x["last_preview_at"] = None
    x["last_preview_candidate_count"] = None
    x["last_preview_outcome"] = None
    x["last_preview_error"] = None
    return x


def build_configuration_bundle(session: Session) -> dict[str, Any]:
    suite_row = ensure_suite_settings_row(session)
    arr_library = session.get(ArrLibraryOperatorSettingsRow, 1)
    ref_op = session.get(RefinerOperatorSettingsRow, 1)
    libraries = list(session.scalars(select(RefinerLibraryRow).order_by(RefinerLibraryRow.id)).all())
    rule_sets = list(session.scalars(select(RefinerRuleSetRow).order_by(RefinerRuleSetRow.id)).all())
    pruner_instances = list(session.scalars(select(PrunerServerInstance).order_by(PrunerServerInstance.id)).all())
    pruner_scopes = list(session.scalars(select(PrunerScopeSettings).order_by(PrunerScopeSettings.id)).all())

    def _req(row: Any | None, label: str) -> Any:
        if row is None:
            msg = f"Missing required configuration row: {label}"
            raise ValueError(msg)
        return row

    return {
        "format_version": BUNDLE_FORMAT_VERSION,
        "suite_settings": orm_row_to_dict(suite_row),
        "arr_library_operator_settings": orm_row_to_dict(_req(arr_library, "arr_library_operator_settings")),
        "refiner_operator_settings": orm_row_to_dict(_req(ref_op, "refiner_operator_settings")),
        "refiner_rule_sets": [orm_row_to_dict(r) for r in rule_sets],
        "refiner_libraries": [orm_row_to_dict(r) for r in libraries],
        "pruner_server_instances": [orm_row_to_dict(r) for r in pruner_instances],
        "pruner_scope_settings": [_sanitize_pruner_scope_export(orm_row_to_dict(r)) for r in pruner_scopes],
    }


def _apply_singleton(session: Session, model_cls: type[T], data: dict[str, Any]) -> None:
    kwargs = dict_to_model_kwargs(model_cls, data)
    pk = kwargs.get("id")
    row = session.get(model_cls, pk) if pk is not None else None
    if row is None:
        row = model_cls(**kwargs)
        session.add(row)
    else:
        for k, v in kwargs.items():
            setattr(row, k, v)


def _restore_refiner_libraries(session: Session, bundle: dict[str, Any]) -> None:
    """Restore Refiner's configuration, from either bundle shape.

    A v4 bundle carries the libraries and rule sets themselves and is restored wholesale.
    A v3 bundle predates #363 and carries the two singleton settings tables instead; its
    values are translated onto the seeded libraries using the same mapping migration 0011
    applied. A backup taken the day before an upgrade has to remain restorable, and
    refusing it over a storage change would be the wrong answer.
    """

    if "refiner_libraries" in bundle:
        # Replaced wholesale, like the Pruner sections above: a restore is "make it look
        # like the backup", not "merge with whatever is here".
        session.execute(delete(RefinerLibraryRow))
        session.execute(delete(RefinerRuleSetRow))
        session.flush()
        for row in bundle.get("refiner_rule_sets", []):
            session.add(RefinerRuleSetRow(**dict_to_model_kwargs(RefinerRuleSetRow, row)))
        session.flush()
        for row in bundle["refiner_libraries"]:
            session.add(RefinerLibraryRow(**dict_to_model_kwargs(RefinerLibraryRow, row)))
        session.flush()
        return

    legacy_paths = bundle.get("refiner_path_settings") or {}
    legacy_rules = bundle.get("refiner_remux_rules_settings") or {}
    if not legacy_paths and not legacy_rules:
        return

    for scope, prefix in (("movie", ""), ("tv", "tv_")):
        library = resolve_library(session, media_scope=scope)
        if library is None:
            continue
        watched = legacy_paths.get(f"refiner_{prefix}watched_folder")
        work = legacy_paths.get(f"refiner_{prefix}work_folder")
        output = legacy_paths.get(f"refiner_{prefix}output_folder")
        if watched is not None:
            library.watched_folder = str(watched or "")
        if work is not None:
            library.work_folder = str(work or "")
        if output is not None:
            library.output_folder = str(output or "")
        interval = legacy_paths.get(f"{'tv' if scope == 'tv' else 'movie'}_watched_folder_check_interval_seconds")
        if interval is not None:
            library.scan_interval_seconds = int(interval)

        rule_set = session.get(RefinerRuleSetRow, library.rule_set_id) if library.rule_set_id else None
        if rule_set is None or not legacy_rules:
            continue
        for field, legacy_key in (
            ("primary_audio_lang", f"{prefix}primary_audio_lang"),
            ("secondary_audio_lang", f"{prefix}secondary_audio_lang"),
            ("tertiary_audio_lang", f"{prefix}tertiary_audio_lang"),
            ("default_audio_slot", f"{prefix}default_audio_slot"),
            ("subtitle_mode", f"{prefix}subtitle_mode"),
            ("subtitle_langs_csv", f"{prefix}subtitle_langs_csv"),
            ("audio_preference_mode", f"{prefix}audio_preference_mode"),
        ):
            value = legacy_rules.get(legacy_key)
            if value is not None:
                setattr(rule_set, field, str(value))
        for field, legacy_key in (
            ("remove_commentary", f"{prefix}remove_commentary"),
            ("preserve_forced_subs", f"{prefix}preserve_forced_subs"),
            ("preserve_default_subs", f"{prefix}preserve_default_subs"),
        ):
            value = legacy_rules.get(legacy_key)
            if value is not None:
                setattr(rule_set, field, bool(value))
    session.flush()


def apply_configuration_bundle(session: Session, bundle: dict[str, Any]) -> None:
    fv = bundle.get("format_version")
    if fv not in SUPPORTED_BUNDLE_FORMAT_VERSIONS:
        supported = ", ".join(str(v) for v in SUPPORTED_BUNDLE_FORMAT_VERSIONS)
        msg = f"Unsupported configuration bundle format_version (this build reads {supported})."
        raise ValueError(msg)

    required = (
        "suite_settings",
        "arr_library_operator_settings",
        "refiner_operator_settings",
        "pruner_server_instances",
        "pruner_scope_settings",
    )
    for key in required:
        if key not in bundle:
            msg = f"Bundle is missing required section: {key}"
            raise ValueError(msg)

    ss = bundle["suite_settings"]
    apply_suite_settings_put(
        session,
        product_display_name=str(ss["product_display_name"]),
        signed_in_home_notice=ss.get("signed_in_home_notice"),
        app_timezone=str(ss["app_timezone"]),
        log_retention_days=int(ss["log_retention_days"]),
        configuration_backup_enabled=ss.get("configuration_backup_enabled"),
        configuration_backup_interval_hours=ss.get("configuration_backup_interval_hours"),
    )

    _apply_singleton(session, ArrLibraryOperatorSettingsRow, bundle["arr_library_operator_settings"])
    _apply_singleton(session, RefinerOperatorSettingsRow, bundle["refiner_operator_settings"])
    _restore_refiner_libraries(session, bundle)

    session.execute(delete(PrunerScopeSettings))
    session.execute(delete(PrunerServerInstance))
    session.flush()
    for row in bundle["pruner_server_instances"]:
        session.add(PrunerServerInstance(**dict_to_model_kwargs(PrunerServerInstance, row)))
    session.flush()
    for row in bundle["pruner_scope_settings"]:
        kwargs = dict_to_model_kwargs(PrunerScopeSettings, row)
        kwargs["last_preview_run_id"] = None
        kwargs["last_preview_at"] = None
        kwargs["last_preview_candidate_count"] = None
        kwargs["last_preview_outcome"] = None
        kwargs["last_preview_error"] = None
        session.add(PrunerScopeSettings(**kwargs))
