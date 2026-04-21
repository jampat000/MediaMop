"""Build and apply JSON configuration bundles (suite + module settings rows)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

from sqlalchemy import DateTime, delete, inspect, select
from sqlalchemy.orm import Session

from mediamop.modules.broker.broker_arr_connections_model import BrokerArrConnectionRow
from mediamop.modules.broker.broker_indexers_model import BrokerIndexerRow
from mediamop.modules.broker.broker_settings_model import BrokerSettingsRow
from mediamop.modules.fetcher.cleanup_policy_model import FetcherFailedImportCleanupPolicyRow
from mediamop.modules.fetcher.fetcher_arr_operator_settings_model import FetcherArrOperatorSettingsRow
from mediamop.modules.fetcher.fetcher_search_schedule_state_model import FetcherSearchScheduleStateRow
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings
from mediamop.modules.pruner.pruner_server_instance_model import PrunerServerInstance
from mediamop.modules.refiner.refiner_operator_settings_model import RefinerOperatorSettingsRow
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow
from mediamop.modules.refiner.refiner_remux_rules_settings_model import RefinerRemuxRulesSettingsRow
from mediamop.modules.subber.subber_providers_model import SubberProviderRow
from mediamop.modules.subber.subber_settings_model import SubberSettingsRow
from mediamop.platform.suite_settings.model import SuiteSettingsRow
from mediamop.platform.suite_settings.service import apply_suite_settings_put, ensure_suite_settings_row

BUNDLE_FORMAT_VERSION = 1

T = TypeVar("T")


def _serialize_cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


def orm_row_to_dict(obj: Any) -> dict[str, Any]:
    mapper = inspect(obj.__class__).mapper
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
    mapper = inspect(model_cls).mapper
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
    fetcher_arr = session.get(FetcherArrOperatorSettingsRow, 1)
    fetcher_policy = session.get(FetcherFailedImportCleanupPolicyRow, 1)
    fetcher_sched = session.get(FetcherSearchScheduleStateRow, 1)
    ref_op = session.get(RefinerOperatorSettingsRow, 1)
    ref_path = session.get(RefinerPathSettingsRow, 1)
    ref_remux = session.get(RefinerRemuxRulesSettingsRow, 1)
    br_settings = session.get(BrokerSettingsRow, 1)
    br_indexers = list(session.scalars(select(BrokerIndexerRow).order_by(BrokerIndexerRow.id)).all())
    br_arr = list(session.scalars(select(BrokerArrConnectionRow).order_by(BrokerArrConnectionRow.id)).all())
    sub_settings = session.get(SubberSettingsRow, 1)
    sub_providers = list(session.scalars(select(SubberProviderRow).order_by(SubberProviderRow.id)).all())
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
        "fetcher_arr_operator_settings": orm_row_to_dict(_req(fetcher_arr, "fetcher_arr_operator_settings")),
        "fetcher_failed_import_cleanup_policy": orm_row_to_dict(_req(fetcher_policy, "fetcher_failed_import_cleanup_policy")),
        "fetcher_search_schedule_state": orm_row_to_dict(_req(fetcher_sched, "fetcher_search_schedule_state")),
        "refiner_operator_settings": orm_row_to_dict(_req(ref_op, "refiner_operator_settings")),
        "refiner_path_settings": orm_row_to_dict(_req(ref_path, "refiner_path_settings")),
        "refiner_remux_rules_settings": orm_row_to_dict(_req(ref_remux, "refiner_remux_rules_settings")),
        "broker_settings": orm_row_to_dict(_req(br_settings, "broker_settings")),
        "broker_indexers": [orm_row_to_dict(r) for r in br_indexers],
        "broker_arr_connections": [orm_row_to_dict(r) for r in br_arr],
        "subber_settings": orm_row_to_dict(_req(sub_settings, "subber_settings")),
        "subber_providers": [orm_row_to_dict(r) for r in sub_providers],
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


def apply_configuration_bundle(session: Session, bundle: dict[str, Any]) -> None:
    if bundle.get("format_version") != BUNDLE_FORMAT_VERSION:
        msg = f"Unsupported configuration bundle format_version (expected {BUNDLE_FORMAT_VERSION})."
        raise ValueError(msg)

    required = (
        "suite_settings",
        "fetcher_arr_operator_settings",
        "fetcher_failed_import_cleanup_policy",
        "fetcher_search_schedule_state",
        "refiner_operator_settings",
        "refiner_path_settings",
        "refiner_remux_rules_settings",
        "broker_settings",
        "broker_indexers",
        "broker_arr_connections",
        "subber_settings",
        "subber_providers",
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

    _apply_singleton(session, FetcherArrOperatorSettingsRow, bundle["fetcher_arr_operator_settings"])
    _apply_singleton(session, FetcherFailedImportCleanupPolicyRow, bundle["fetcher_failed_import_cleanup_policy"])
    _apply_singleton(session, FetcherSearchScheduleStateRow, bundle["fetcher_search_schedule_state"])
    _apply_singleton(session, RefinerOperatorSettingsRow, bundle["refiner_operator_settings"])
    _apply_singleton(session, RefinerPathSettingsRow, bundle["refiner_path_settings"])
    _apply_singleton(session, RefinerRemuxRulesSettingsRow, bundle["refiner_remux_rules_settings"])
    _apply_singleton(session, BrokerSettingsRow, bundle["broker_settings"])
    _apply_singleton(session, SubberSettingsRow, bundle["subber_settings"])

    session.execute(delete(BrokerIndexerRow))
    for row in bundle["broker_indexers"]:
        session.add(BrokerIndexerRow(**dict_to_model_kwargs(BrokerIndexerRow, row)))

    session.execute(delete(BrokerArrConnectionRow))
    for row in bundle["broker_arr_connections"]:
        session.add(BrokerArrConnectionRow(**dict_to_model_kwargs(BrokerArrConnectionRow, row)))

    session.execute(delete(SubberProviderRow))
    for row in bundle["subber_providers"]:
        session.add(SubberProviderRow(**dict_to_model_kwargs(SubberProviderRow, row)))

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
