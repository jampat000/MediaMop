"""Durable Refiner job kinds for what happens once a file has used up its retries (#465, #471)."""

from __future__ import annotations

# Hand the unmodified original back to the output folder.
REFINER_FILE_PASS_THROUGH_JOB_KIND = "refiner.file.pass_through.v1"
# Tell the manager the release is bad; falls back to a pass-through when that cannot be done safely.
REFINER_FILE_REJECT_JOB_KIND = "refiner.file.reject.v1"
