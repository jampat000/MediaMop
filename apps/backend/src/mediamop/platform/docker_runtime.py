"""Docker runtime ownership helpers for Linux container launches."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _first_env(env: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        raw = str(env.get(name, "")).strip()
        if raw:
            return raw
    return None


def _parse_non_negative_int(raw: str, *, name: str) -> int:
    if not raw.isdigit():
        raise ValueError(f"{name} must be a non-negative integer.")
    return int(raw)


def _parse_boolish(raw: str | None, *, name: str, default: bool) -> bool:
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be one of: true/false, 1/0, yes/no, on/off.")


def _parse_directory_mode(raw: str | None, *, name: str) -> int | None:
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    if len(value) not in {3, 4} or any(ch not in "01234567" for ch in value):
        raise ValueError(f"{name} must be an octal directory mode such as 775 or 2775.")
    return int(value, 8)


@dataclass(frozen=True, slots=True)
class DockerOwnershipPlan:
    puid: int
    pgid: int
    chown_watched: bool
    chown_temp: bool
    chown_output: bool
    watched_dir_mode: int | None
    temp_dir_mode: int | None
    output_dir_mode: int | None


def load_docker_ownership_plan(
    env: Mapping[str, str] | None = None,
) -> DockerOwnershipPlan:
    values = dict(os.environ if env is None else env)
    puid = _parse_non_negative_int(
        _first_env(values, "MEDIAMOP_PUID", "PUID") or "1000",
        name="MEDIAMOP_PUID",
    )
    pgid = _parse_non_negative_int(
        _first_env(values, "MEDIAMOP_PGID", "PGID") or "1000",
        name="MEDIAMOP_PGID",
    )
    return DockerOwnershipPlan(
        puid=puid,
        pgid=pgid,
        chown_watched=_parse_boolish(
            values.get("MEDIAMOP_CHOWN_WATCHED"),
            name="MEDIAMOP_CHOWN_WATCHED",
            default=False,
        ),
        chown_temp=_parse_boolish(
            values.get("MEDIAMOP_CHOWN_TEMP"),
            name="MEDIAMOP_CHOWN_TEMP",
            default=False,
        ),
        chown_output=_parse_boolish(
            values.get("MEDIAMOP_CHOWN_OUTPUT"),
            name="MEDIAMOP_CHOWN_OUTPUT",
            default=False,
        ),
        watched_dir_mode=_parse_directory_mode(
            values.get("MEDIAMOP_DIR_MODE_WATCHED"),
            name="MEDIAMOP_DIR_MODE_WATCHED",
        ),
        temp_dir_mode=_parse_directory_mode(
            values.get("MEDIAMOP_DIR_MODE_TEMP"),
            name="MEDIAMOP_DIR_MODE_TEMP",
        ),
        output_dir_mode=_parse_directory_mode(
            values.get("MEDIAMOP_DIR_MODE_OUTPUT"),
            name="MEDIAMOP_DIR_MODE_OUTPUT",
        ),
    )


def _dedupe_paths(values: list[str | None]) -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        path = Path(text).expanduser().resolve(strict=False)
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def collect_refiner_permission_targets(
    db_path: Path,
    *,
    include_watched: bool,
    include_temp: bool,
    include_output: bool,
) -> dict[str, list[Path]]:
    targets: dict[str, list[Path]] = {"watched": [], "temp": [], "output": []}
    resolved_db = db_path.expanduser().resolve(strict=False)
    if not resolved_db.is_file():
        return targets
    try:
        with sqlite3.connect(resolved_db) as conn:
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'refiner_path_settings'",
            ).fetchone()
            if table is None:
                return targets
            row = conn.execute(
                """
                SELECT
                    refiner_watched_folder,
                    refiner_work_folder,
                    refiner_output_folder,
                    refiner_tv_watched_folder,
                    refiner_tv_work_folder,
                    refiner_tv_output_folder
                FROM refiner_path_settings
                WHERE id = 1
                """,
            ).fetchone()
    except sqlite3.Error:
        return targets
    if row is None:
        return targets
    watched_movie, temp_movie, output_movie, watched_tv, temp_tv, output_tv = row
    if include_watched:
        targets["watched"] = _dedupe_paths([watched_movie, watched_tv])
    if include_temp:
        targets["temp"] = _dedupe_paths([temp_movie, temp_tv])
    if include_output:
        targets["output"] = _dedupe_paths([output_movie, output_tv])
    return targets


def _chown_tree(root: Path, *, uid: int, gid: int) -> None:
    if not hasattr(os, "chown"):
        raise RuntimeError("Recursive ownership changes require POSIX os.chown support.")
    for current_root, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current_root)
        os.chown(current_path, uid, gid, follow_symlinks=False)
        for name in dirnames:
            path = current_path / name
            if path.is_symlink():
                continue
            os.chown(path, uid, gid, follow_symlinks=False)
        for name in filenames:
            path = current_path / name
            if path.is_symlink():
                continue
            os.chown(path, uid, gid, follow_symlinks=False)


def _chmod_directories(root: Path, *, mode: int) -> None:
    for current_root, dirnames, _filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current_root)
        os.chmod(current_path, mode, follow_symlinks=False)
        for name in dirnames:
            path = current_path / name
            if path.is_symlink():
                continue
            os.chmod(path, mode, follow_symlinks=False)


def apply_refiner_permissions(
    *,
    db_path: Path,
    plan: DockerOwnershipPlan,
) -> list[str]:
    messages: list[str] = []
    include_watched = plan.chown_watched or plan.watched_dir_mode is not None
    include_temp = plan.chown_temp or plan.temp_dir_mode is not None
    include_output = plan.chown_output or plan.output_dir_mode is not None
    targets = collect_refiner_permission_targets(
        db_path,
        include_watched=include_watched,
        include_temp=include_temp,
        include_output=include_output,
    )
    mode_map = {
        "watched": plan.watched_dir_mode,
        "temp": plan.temp_dir_mode,
        "output": plan.output_dir_mode,
    }
    chown_map = {
        "watched": plan.chown_watched,
        "temp": plan.chown_temp,
        "output": plan.chown_output,
    }
    for kind in ("watched", "temp", "output"):
        for path in targets[kind]:
            if not path.exists():
                messages.append(f"{kind}: skipped missing path {path}")
                continue
            if not path.is_dir():
                raise RuntimeError(f"{kind} path is not a directory: {path}")
            if chown_map[kind]:
                _chown_tree(path, uid=plan.puid, gid=plan.pgid)
                messages.append(f"{kind}: updated ownership for {path}")
            mode = mode_map[kind]
            if mode is not None:
                _chmod_directories(path, mode=mode)
                messages.append(f"{kind}: applied directory mode {mode:o} to {path}")
    return messages


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    targets = sub.add_parser("print-refiner-targets")
    targets.add_argument("--db-path", required=True)
    targets.add_argument("--include-watched", action="store_true")
    targets.add_argument("--include-temp", action="store_true")
    targets.add_argument("--include-output", action="store_true")

    apply = sub.add_parser("apply-refiner-permissions")
    apply.add_argument("--db-path", required=True)
    apply.add_argument("--uid", required=True)
    apply.add_argument("--gid", required=True)
    apply.add_argument("--include-watched", action="store_true")
    apply.add_argument("--include-temp", action="store_true")
    apply.add_argument("--include-output", action="store_true")
    apply.add_argument("--watched-dir-mode")
    apply.add_argument("--temp-dir-mode")
    apply.add_argument("--output-dir-mode")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    db_path = Path(args.db_path)
    if args.command == "print-refiner-targets":
        data = collect_refiner_permission_targets(
            db_path,
            include_watched=bool(args.include_watched),
            include_temp=bool(args.include_temp),
            include_output=bool(args.include_output),
        )
        print(
            json.dumps(
                {kind: [str(path) for path in paths] for kind, paths in data.items()},
                separators=(",", ":"),
            )
        )
        return 0

    plan = DockerOwnershipPlan(
        puid=_parse_non_negative_int(str(args.uid), name="--uid"),
        pgid=_parse_non_negative_int(str(args.gid), name="--gid"),
        chown_watched=bool(args.include_watched),
        chown_temp=bool(args.include_temp),
        chown_output=bool(args.include_output),
        watched_dir_mode=_parse_directory_mode(args.watched_dir_mode, name="--watched-dir-mode"),
        temp_dir_mode=_parse_directory_mode(args.temp_dir_mode, name="--temp-dir-mode"),
        output_dir_mode=_parse_directory_mode(args.output_dir_mode, name="--output-dir-mode"),
    )
    for line in apply_refiner_permissions(db_path=db_path, plan=plan):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
