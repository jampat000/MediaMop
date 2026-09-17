-- Weir schema 0004 (issue #557, revision 0039_library_files): the library-mode scan index and #551
-- manager-match data move off the latest completed "refiner.library.scan.v1" job's payload_json onto a
-- real table, so job-row retention can no longer delete a library's file index.

CREATE TABLE library_files (
	id INTEGER NOT NULL,
	library_id INTEGER NOT NULL,
	path TEXT NOT NULL,
	size_bytes BIGINT DEFAULT '0' NOT NULL,
	mtime BIGINT DEFAULT '0' NOT NULL,
	classification TEXT DEFAULT 'cannot_process' NOT NULL,
	summary TEXT,
	reason TEXT,
	removed_audio_tracks INTEGER DEFAULT '0' NOT NULL,
	removed_subtitle_tracks INTEGER DEFAULT '0' NOT NULL,
	estimated_bytes_saved BIGINT DEFAULT '0' NOT NULL,
	manager_kind TEXT,
	manager_title TEXT,
	manager_connection_id INTEGER,
	manager_title_id TEXT,
	manager_file_id INTEGER,
	manager_quality_profile_id INTEGER,
	probe_json TEXT,
	scanned_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_library_files PRIMARY KEY (id),
	CONSTRAINT uq_library_files_library_id_path UNIQUE (library_id, path),
	CONSTRAINT fk_library_files_refiner_libraries_library_id FOREIGN KEY(library_id) REFERENCES refiner_libraries (id) ON DELETE CASCADE,
	CONSTRAINT fk_library_files_media_manager_connections_manager_connection_id FOREIGN KEY(manager_connection_id) REFERENCES media_manager_connections (id) ON DELETE SET NULL
);

CREATE INDEX ix_library_files_library_id ON library_files (library_id);
CREATE INDEX ix_library_files_library_id_classification ON library_files (library_id, classification);

-- Copy the latest completed scan's file list for each library (Weir.Core.LibraryMode.LibraryScanSnapshot,
-- keyed scan_result.files[]) into the table.
WITH scans AS (
	SELECT id, CAST(json_extract(payload_json, '$.library_id') AS INTEGER) AS library_id, payload_json
	FROM refiner_jobs
	WHERE job_kind = 'refiner.library.scan.v1' AND status = 'completed'
),
latest_scan_ids AS (
	SELECT library_id, MAX(id) AS id FROM scans GROUP BY library_id
),
latest AS (
	SELECT scans.library_id, scans.payload_json
	FROM scans
	JOIN latest_scan_ids ON latest_scan_ids.library_id = scans.library_id AND latest_scan_ids.id = scans.id
)
INSERT INTO library_files (
	library_id, path, size_bytes, mtime, classification, summary, reason, removed_audio_tracks,
	removed_subtitle_tracks, estimated_bytes_saved, manager_kind, manager_title, manager_connection_id,
	manager_title_id, manager_file_id, manager_quality_profile_id, probe_json
)
SELECT
	latest.library_id,
	json_extract(file.value, '$.path'),
	COALESCE(json_extract(file.value, '$.size_bytes'), 0),
	COALESCE(json_extract(file.value, '$.mtime'), 0),
	COALESCE(json_extract(file.value, '$.classification'), 'cannot_process'),
	json_extract(file.value, '$.summary'),
	json_extract(file.value, '$.reason'),
	COALESCE(json_extract(file.value, '$.removed_audio_tracks'), 0),
	COALESCE(json_extract(file.value, '$.removed_subtitle_tracks'), 0),
	COALESCE(json_extract(file.value, '$.estimated_bytes_saved'), 0),
	json_extract(file.value, '$.manager_kind'),
	json_extract(file.value, '$.manager_title'),
	json_extract(file.value, '$.manager_connection_id'),
	json_extract(file.value, '$.manager_title_id'),
	json_extract(file.value, '$.manager_file_id'),
	json_extract(file.value, '$.manager_quality_profile_id'),
	json_extract(file.value, '$.probe_json')
FROM latest, json_each(latest.payload_json, '$.scan_result.files') AS file
WHERE json_extract(file.value, '$.path') IS NOT NULL AND latest.library_id IN (SELECT id FROM refiner_libraries);

-- The big per-file array is now redundant on the job row; strip it (keeping the job's own small
-- ok/generated_at/errors outcome, which stays exactly the kind of thing job-row retention may prune).
UPDATE refiner_jobs
SET payload_json = json_remove(payload_json, '$.scan_result.files')
WHERE job_kind = 'refiner.library.scan.v1' AND json_extract(payload_json, '$.scan_result.files') IS NOT NULL;
