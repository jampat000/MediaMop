-- Weir schema 0006 (issue #557, revision 0041_removed_tracks): issue #509's removed-track records move off
-- refiner_file_logs.detail_json (Weir.Infrastructure.Library.FileLogRemovedTrackStore) onto a real table, one
-- row per removed track, so a file's removed-track history survives file-log retention.

CREATE TABLE removed_tracks (
	id INTEGER NOT NULL,
	library_id INTEGER,
	relative_path TEXT NOT NULL,
	language TEXT DEFAULT 'und' NOT NULL,
	track_type TEXT DEFAULT 'audio' NOT NULL,
	codec TEXT DEFAULT 'unknown' NOT NULL,
	variant TEXT,
	reason TEXT DEFAULT '' NOT NULL,
	recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_removed_tracks PRIMARY KEY (id),
	CONSTRAINT fk_removed_tracks_refiner_libraries_library_id FOREIGN KEY(library_id) REFERENCES refiner_libraries (id) ON DELETE SET NULL
);

CREATE INDEX ix_removed_tracks_library_id_relative_path ON removed_tracks (library_id, relative_path);

-- Copy the newest refiner_file_logs row's removed-track data for every (library_id, relative_path), the
-- same "latest wins" rule FileLogRemovedTrackStore.GetAsync/GetAllAsync already read with. The structured
-- "removed_track_records" shape (Weir.Infrastructure.Library.FileLogRemovedTrackStore.RecordAsync, the only
-- writer in this codebase) is preferred; a row with only the legacy removed_audio/removed_subtitles string
-- arrays (written by the retired Python backend) is parsed the same best-effort way
-- FileLogRemovedTrackStore.AddLegacy did.
WITH file_logs AS (
	SELECT
		library_id, relative_path, detail_json,
		ROW_NUMBER() OVER (PARTITION BY library_id, relative_path ORDER BY recorded_at DESC, id DESC) AS rn
	FROM refiner_file_logs
),
latest AS (
	SELECT library_id, relative_path, detail_json
	FROM file_logs
	WHERE rn = 1 AND json_valid(detail_json)
)
INSERT INTO removed_tracks (library_id, relative_path, language, track_type, codec, variant, reason)
SELECT
	latest.library_id,
	latest.relative_path,
	COALESCE(json_extract(track.value, '$.language'), 'und'),
	CASE WHEN json_extract(track.value, '$.type') = 'subtitle' THEN 'subtitle' ELSE 'audio' END,
	COALESCE(json_extract(track.value, '$.codec'), 'unknown'),
	json_extract(track.value, '$.variant'),
	COALESCE(json_extract(track.value, '$.reason'), '')
FROM latest, json_each(latest.detail_json, '$.removed_track_records') AS track
WHERE json_extract(latest.detail_json, '$.removed_track_records') IS NOT NULL
  AND (latest.library_id IS NULL OR latest.library_id IN (SELECT id FROM refiner_libraries));

WITH file_logs AS (
	SELECT
		library_id, relative_path, detail_json,
		ROW_NUMBER() OVER (PARTITION BY library_id, relative_path ORDER BY recorded_at DESC, id DESC) AS rn
	FROM refiner_file_logs
),
latest AS (
	SELECT library_id, relative_path, detail_json
	FROM file_logs
	WHERE rn = 1 AND json_valid(detail_json) AND json_extract(detail_json, '$.removed_track_records') IS NULL
	  AND (library_id IS NULL OR library_id IN (SELECT id FROM refiner_libraries))
)
INSERT INTO removed_tracks (library_id, relative_path, language, track_type, codec, variant, reason)
SELECT
	latest.library_id,
	latest.relative_path,
	CASE WHEN instr(track.value || ' ', ' ') > 1 THEN TRIM(substr(track.value, 1, instr(track.value || ' ', ' ') - 1), ':') ELSE 'und' END,
	'audio',
	'unknown',
	NULL,
	track.value
FROM latest, json_each(latest.detail_json, '$.removed_audio') AS track
WHERE json_extract(latest.detail_json, '$.removed_audio') IS NOT NULL
UNION ALL
SELECT
	latest.library_id,
	latest.relative_path,
	CASE WHEN instr(track.value || ' ', ' ') > 1 THEN TRIM(substr(track.value, 1, instr(track.value || ' ', ' ') - 1), ':') ELSE 'und' END,
	'subtitle',
	'unknown',
	NULL,
	track.value
FROM latest, json_each(latest.detail_json, '$.removed_subtitles') AS track
WHERE json_extract(latest.detail_json, '$.removed_subtitles') IS NOT NULL;
