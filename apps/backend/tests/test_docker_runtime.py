from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mediamop.platform.docker_runtime import (
    collect_refiner_permission_targets,
    load_docker_ownership_plan,
)


def _seed_refiner_path_settings(db_path: Path, *, root: Path) -> dict[str, Path]:
    paths = {
        "movies_watch": root / "movies-watch",
        "movies_temp": root / "movies-temp",
        "movies_out": root / "movies-out",
        "tv_watch": root / "tv-watch",
        "tv_temp": root / "tv-temp",
        "tv_out": root / "tv-out",
    }
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE refiner_path_settings (
                id INTEGER PRIMARY KEY,
                refiner_watched_folder TEXT,
                refiner_work_folder TEXT,
                refiner_output_folder TEXT NOT NULL DEFAULT '',
                refiner_tv_watched_folder TEXT,
                refiner_tv_work_folder TEXT,
                refiner_tv_output_folder TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO refiner_path_settings (
                id,
                refiner_watched_folder,
                refiner_work_folder,
                refiner_output_folder,
                refiner_tv_watched_folder,
                refiner_tv_work_folder,
                refiner_tv_output_folder
            ) VALUES (1, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(paths["movies_watch"]),
                str(paths["movies_temp"]),
                str(paths["movies_out"]),
                str(paths["tv_watch"]),
                str(paths["tv_temp"]),
                str(paths["tv_out"]),
            ),
        )
        conn.commit()
    return paths


def test_load_docker_ownership_plan_accepts_alias_env_names() -> None:
    plan = load_docker_ownership_plan(
        {
            "PUID": "1001",
            "PGID": "1002",
            "MEDIAMOP_CHOWN_OUTPUT": "true",
            "MEDIAMOP_DIR_MODE_OUTPUT": "2775",
        }
    )

    assert plan.puid == 1001
    assert plan.pgid == 1002
    assert plan.chown_output is True
    assert plan.output_dir_mode == 0o2775


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MEDIAMOP_PUID", "-1"),
        ("MEDIAMOP_PGID", "abc"),
        ("MEDIAMOP_CHOWN_OUTPUT", "sometimes"),
        ("MEDIAMOP_DIR_MODE_OUTPUT", "27x5"),
    ],
)
def test_load_docker_ownership_plan_rejects_invalid_values(
    name: str,
    value: str,
) -> None:
    with pytest.raises(ValueError):
        load_docker_ownership_plan({name: value})


def test_collect_refiner_permission_targets_groups_movie_and_tv_paths(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "data" / "mediamop.sqlite3"
    paths = _seed_refiner_path_settings(db_path, root=tmp_path / "mounted")

    targets = collect_refiner_permission_targets(
        db_path,
        include_watched=True,
        include_temp=True,
        include_output=True,
    )

    assert [str(path) for path in targets["watched"]] == [
        str(paths["movies_watch"].resolve(strict=False)),
        str(paths["tv_watch"].resolve(strict=False)),
    ]
    assert [str(path) for path in targets["temp"]] == [
        str(paths["movies_temp"].resolve(strict=False)),
        str(paths["tv_temp"].resolve(strict=False)),
    ]
    assert [str(path) for path in targets["output"]] == [
        str(paths["movies_out"].resolve(strict=False)),
        str(paths["tv_out"].resolve(strict=False)),
    ]


def test_collect_refiner_permission_targets_is_empty_without_table(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "data" / "mediamop.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path):
        pass

    targets = collect_refiner_permission_targets(
        db_path,
        include_watched=True,
        include_temp=True,
        include_output=True,
    )

    assert targets == {"watched": [], "temp": [], "output": []}
