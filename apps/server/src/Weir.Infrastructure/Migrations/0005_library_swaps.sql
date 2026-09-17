-- Weir schema 0005 (issue #557, revision 0040_library_swaps): the #506 safe-swap journal moves off the
-- "library_swap"/"swap_committed" keys RefinerJobSwapJournal packed into refiner_jobs.payload_json onto a
-- real table, one row per job, that the startup recovery sweep reads directly.

CREATE TABLE library_swaps (
	job_id INTEGER NOT NULL,
	state TEXT NOT NULL,
	original_path TEXT NOT NULL,
	temp_path TEXT NOT NULL,
	backup_path TEXT NOT NULL,
	committed BOOLEAN DEFAULT '0' NOT NULL,
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_library_swaps PRIMARY KEY (job_id),
	CONSTRAINT fk_library_swaps_refiner_jobs_job_id FOREIGN KEY(job_id) REFERENCES refiner_jobs (id) ON DELETE CASCADE
);

-- Copy every job row's swap record (the "library_swap" object, plus "swap_committed") into the table.
INSERT INTO library_swaps (job_id, state, original_path, temp_path, backup_path, committed)
SELECT
	id,
	json_extract(payload_json, '$.library_swap.state'),
	json_extract(payload_json, '$.library_swap.original_path'),
	json_extract(payload_json, '$.library_swap.temp_path'),
	json_extract(payload_json, '$.library_swap.backup_path'),
	COALESCE(json_extract(payload_json, '$.swap_committed'), 0)
FROM refiner_jobs
WHERE json_extract(payload_json, '$.library_swap.state') IS NOT NULL
  AND json_extract(payload_json, '$.library_swap.original_path') IS NOT NULL;

-- The journal is fully superseded by the table above; strip its keys from the job payload.
UPDATE refiner_jobs
SET payload_json = json_remove(payload_json, '$.library_swap', '$.swap_committed')
WHERE json_extract(payload_json, '$.library_swap') IS NOT NULL;
