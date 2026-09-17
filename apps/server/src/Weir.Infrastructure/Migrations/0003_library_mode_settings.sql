-- Weir schema 0003 (issue #557, revision 0038_library_mode_settings): library mode's (#505) per-library
-- settings move off the one permanent refiner_jobs row per library (job_kind
-- "refiner.library.settings.v1") onto real columns and a real folders table, so job-row retention can no
-- longer delete them.

ALTER TABLE refiner_libraries ADD COLUMN library_schedule_enabled BOOLEAN DEFAULT '0' NOT NULL;
ALTER TABLE refiner_libraries ADD COLUMN clean_hardlinked_files BOOLEAN DEFAULT '0' NOT NULL;
ALTER TABLE refiner_libraries ADD COLUMN skip_if_manager_would_redownload BOOLEAN DEFAULT '1' NOT NULL;

CREATE TABLE library_folders (
	id INTEGER NOT NULL,
	library_id INTEGER NOT NULL,
	folder TEXT NOT NULL,
	position INTEGER DEFAULT '0' NOT NULL,
	CONSTRAINT pk_library_folders PRIMARY KEY (id),
	CONSTRAINT uq_library_folders_library_id_folder UNIQUE (library_id, folder),
	CONSTRAINT fk_library_folders_refiner_libraries_library_id FOREIGN KEY(library_id) REFERENCES refiner_libraries (id) ON DELETE CASCADE
);

CREATE INDEX ix_library_folders_library_id ON library_folders (library_id);

-- Copy every library's settings row (payload: library_id, library_folders, library_schedule_enabled,
-- clean_hardlinked_files, skip_if_manager_would_redownload -- see Weir.Core.LibraryMode.LibrarySettings)
-- onto its refiner_libraries row. A library with no settings row keeps the defaults just applied above.
UPDATE refiner_libraries
SET
	library_schedule_enabled = COALESCE((
		SELECT json_extract(j.payload_json, '$.library_schedule_enabled')
		FROM refiner_jobs j WHERE j.job_kind = 'refiner.library.settings.v1' AND j.dedupe_key = 'refiner.library.settings.v1:' || refiner_libraries.id
	), 0),
	clean_hardlinked_files = COALESCE((
		SELECT json_extract(j.payload_json, '$.clean_hardlinked_files')
		FROM refiner_jobs j WHERE j.job_kind = 'refiner.library.settings.v1' AND j.dedupe_key = 'refiner.library.settings.v1:' || refiner_libraries.id
	), 0),
	skip_if_manager_would_redownload = COALESCE((
		SELECT json_extract(j.payload_json, '$.skip_if_manager_would_redownload')
		FROM refiner_jobs j WHERE j.job_kind = 'refiner.library.settings.v1' AND j.dedupe_key = 'refiner.library.settings.v1:' || refiner_libraries.id
	), 1)
WHERE EXISTS (
	SELECT 1 FROM refiner_jobs j WHERE j.job_kind = 'refiner.library.settings.v1' AND j.dedupe_key = 'refiner.library.settings.v1:' || refiner_libraries.id
);

INSERT INTO library_folders (library_id, folder, position)
SELECT j.library_id, folder.value, folder.key
FROM (
	SELECT CAST(json_extract(payload_json, '$.library_id') AS INTEGER) AS library_id, payload_json
	FROM refiner_jobs
	WHERE job_kind = 'refiner.library.settings.v1'
) j, json_each(j.payload_json, '$.library_folders') AS folder
WHERE folder.value IS NOT NULL AND folder.value != '' AND j.library_id IN (SELECT id FROM refiner_libraries);

-- The settings row is fully superseded by the columns/table above; drop it rather than leave it as dead,
-- unreadable weight in refiner_jobs.
DELETE FROM refiner_jobs WHERE job_kind = 'refiner.library.settings.v1';
