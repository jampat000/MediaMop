"""Job kinds + dedupe keys for Refiner Pass 4 failure-cleanup sweeps (Movies and TV separate)."""

from __future__ import annotations

REFINER_MOVIE_FAILURE_CLEANUP_SWEEP_JOB_KIND = "refiner.movie_failure_cleanup_sweep.v1"
REFINER_TV_FAILURE_CLEANUP_SWEEP_JOB_KIND = "refiner.tv_failure_cleanup_sweep.v1"

REFINER_MOVIE_FAILURE_CLEANUP_SWEEP_DEDUPE_KEY = "refiner.movie_failure_cleanup_sweep:v1"
REFINER_TV_FAILURE_CLEANUP_SWEEP_DEDUPE_KEY = "refiner.tv_failure_cleanup_sweep:v1"
