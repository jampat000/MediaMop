-- Weir schema 0007 (issue #568, revision 0042_library_file_facets): the Library view needs totals and
-- breakdowns by video codec, resolution class, audio codec/channels and audio/subtitle language over a whole
-- library, and a paged, sortable, facet-filtered file listing. Both are SQL over library_files, never a page of
-- JSON parsed in the browser, so the codec/language facts the scan already cached inside probe_json get their
-- own columns and their own (facet, value) table to group and filter by.
--
-- Nothing here re-probes anything: every value is read out of the ffprobe JSON already on the row, and a row
-- with no usable probe JSON is left reading 'unknown', which is exactly what issue #568 asks for.

ALTER TABLE library_files ADD COLUMN video_codec TEXT;
ALTER TABLE library_files ADD COLUMN video_height INTEGER;
ALTER TABLE library_files ADD COLUMN resolution_class TEXT;
ALTER TABLE library_files ADD COLUMN audio_track_count INTEGER DEFAULT '0' NOT NULL;
ALTER TABLE library_files ADD COLUMN subtitle_track_count INTEGER DEFAULT '0' NOT NULL;
ALTER TABLE library_files ADD COLUMN audio_summary TEXT;
ALTER TABLE library_files ADD COLUMN subtitle_summary TEXT;
ALTER TABLE library_files ADD COLUMN link_count INTEGER;
ALTER TABLE library_files ADD COLUMN problem_kind TEXT;

-- The Files listing sorts by these and filters by classification; the breakdown tables group by them.
CREATE INDEX ix_library_files_library_id_size_bytes ON library_files (library_id, size_bytes);
CREATE INDEX ix_library_files_library_id_video_codec ON library_files (library_id, video_codec);
CREATE INDEX ix_library_files_library_id_resolution_class ON library_files (library_id, resolution_class);
CREATE INDEX ix_library_files_library_id_problem_kind ON library_files (library_id, problem_kind);

-- One row per (file, facet, value). Multi-valued facets (a file's audio shapes and its audio/subtitle
-- languages) cannot live in a column, and a value must be groupable and filterable without opening probe_json.
CREATE TABLE library_file_facets (
	id INTEGER NOT NULL,
	library_id INTEGER NOT NULL,
	library_file_id INTEGER NOT NULL,
	facet TEXT NOT NULL,
	value TEXT NOT NULL,
	CONSTRAINT pk_library_file_facets PRIMARY KEY (id),
	CONSTRAINT uq_library_file_facets_file_facet_value UNIQUE (library_file_id, facet, value),
	CONSTRAINT fk_library_file_facets_library_files_library_file_id FOREIGN KEY(library_file_id) REFERENCES library_files (id) ON DELETE CASCADE,
	CONSTRAINT fk_library_file_facets_refiner_libraries_library_id FOREIGN KEY(library_id) REFERENCES refiner_libraries (id) ON DELETE CASCADE
);

-- The breakdown query (group by value within one library and facet) and the Files filter (every file carrying
-- one value) are the only two shapes this table is ever read in.
CREATE INDEX ix_library_file_facets_library_id_facet_value ON library_file_facets (library_id, facet, value);
CREATE INDEX ix_library_file_facets_library_file_id ON library_file_facets (library_file_id);

-- Back-fill from the probe JSON already on each row, so an install that scanned before this migration gets a
-- populated Library view without waiting for a rescan. These CASE expressions mirror
-- Weir.Core.LibraryMode.LibraryFileFactsReader exactly; Issue568MigrationTests compares the two on the same
-- probe JSON, so a change to one needs the same change to the other.

-- The file's own video stream: the first video stream that is not an attached cover image (a poster is a video
-- stream to ffprobe, and would otherwise report the file's codec as mjpeg).
CREATE TEMP VIEW library_file_video AS
SELECT
	f.id AS library_file_id,
	(
		SELECT s.value FROM json_each(f.probe_json, '$.streams') AS s
		WHERE json_extract(s.value, '$.codec_type') = 'video'
			AND COALESCE(json_extract(s.value, '$.disposition.attached_pic'), 0) = 0
		LIMIT 1
	) AS stream
FROM library_files AS f
WHERE f.probe_json IS NOT NULL AND json_valid(f.probe_json);

UPDATE library_files
SET video_codec = COALESCE(
		NULLIF(LOWER(TRIM(json_extract((SELECT stream FROM library_file_video WHERE library_file_id = library_files.id), '$.codec_name'))), ''),
		'unknown'),
	video_height = json_extract((SELECT stream FROM library_file_video WHERE library_file_id = library_files.id), '$.height')
WHERE id IN (SELECT library_file_id FROM library_file_video);

UPDATE library_files
SET resolution_class = CASE
		WHEN COALESCE(video_height, 0) >= 1700
			OR COALESCE(json_extract((SELECT stream FROM library_file_video WHERE library_file_id = library_files.id), '$.width'), 0) >= 3000 THEN '4k'
		WHEN COALESCE(video_height, 0) >= 1000
			OR COALESCE(json_extract((SELECT stream FROM library_file_video WHERE library_file_id = library_files.id), '$.width'), 0) >= 1800 THEN '1080p'
		WHEN COALESCE(video_height, 0) >= 700
			OR COALESCE(json_extract((SELECT stream FROM library_file_video WHERE library_file_id = library_files.id), '$.width'), 0) >= 1200 THEN '720p'
		WHEN COALESCE(video_height, 0) > 0
			OR COALESCE(json_extract((SELECT stream FROM library_file_video WHERE library_file_id = library_files.id), '$.width'), 0) > 0 THEN 'sd'
		ELSE 'unknown'
	END
WHERE id IN (SELECT library_file_id FROM library_file_video);

-- Every row that had no usable probe JSON to read (or none at all) reports unknown rather than an empty cell.
UPDATE library_files
SET video_codec = COALESCE(video_codec, 'unknown'),
	resolution_class = COALESCE(resolution_class, 'unknown');

UPDATE library_files
SET audio_track_count = (
		SELECT COUNT(*) FROM json_each(library_files.probe_json, '$.streams') AS s
		WHERE json_extract(s.value, '$.codec_type') = 'audio'),
	subtitle_track_count = (
		SELECT COUNT(*) FROM json_each(library_files.probe_json, '$.streams') AS s
		WHERE json_extract(s.value, '$.codec_type') = 'subtitle')
WHERE probe_json IS NOT NULL AND json_valid(probe_json);

-- Weir.Core.Rules.OriginalLanguage's alias table: one canonical spelling per language, so a file tagged "ja"
-- and one tagged "jpn" land on the same breakdown row instead of two. Same groups, same winner (the first
-- entry of each group), in the same order.
CREATE TEMP TABLE library_language_aliases (alias TEXT PRIMARY KEY, canonical TEXT NOT NULL);
INSERT INTO library_language_aliases (alias, canonical) VALUES
	('en', 'eng'),
	('fr', 'fre'), ('fra', 'fre'),
	('de', 'ger'), ('deu', 'ger'),
	('es', 'spa'),
	('it', 'ita'),
	('ja', 'jpn'),
	('ko', 'kor'),
	('zh', 'chi'), ('zho', 'chi'),
	('pt', 'por'),
	('ru', 'rus'),
	('nl', 'dut'), ('nld', 'dut'),
	('sv', 'swe'),
	('da', 'dan'),
	('no', 'nor'),
	('fi', 'fin'),
	('pl', 'pol'),
	('cs', 'cze'), ('ces', 'cze'),
	('hu', 'hun'),
	('tr', 'tur'),
	('ar', 'ara'),
	('he', 'heb'),
	('hi', 'hin'),
	('th', 'tha'),
	('uk', 'ukr'),
	('el', 'gre'), ('ell', 'gre'),
	('ro', 'rum'), ('ron', 'rum'),
	('is', 'ice'), ('isl', 'ice');

-- Each track's facet values, computed once so the inserts below all read the same expressions. Built in three
-- layers because SQLite has no lateral join: each layer names the one before it rather than re-deriving a value.
CREATE TEMP VIEW library_file_streams AS
SELECT f.id AS library_file_id, f.library_id AS library_id, s.value AS stream
FROM library_files AS f, json_each(f.probe_json, '$.streams') AS s
WHERE f.probe_json IS NOT NULL AND json_valid(f.probe_json);

CREATE TEMP VIEW library_file_tracks_raw AS
SELECT
	library_file_id,
	library_id,
	json_extract(stream, '$.codec_type') AS codec_type,
	COALESCE(NULLIF(LOWER(TRIM(json_extract(stream, '$.codec_name'))), ''), 'unknown') AS codec,
	COALESCE(TRIM(json_extract(stream, '$.channel_layout')), '') AS raw_layout,
	COALESCE(json_extract(stream, '$.channels'), 0) AS channels,
	LOWER(TRIM(COALESCE(json_extract(stream, '$.tags.language'), ''))) AS raw_language
FROM library_file_streams;

CREATE TEMP VIEW library_file_tracks AS
SELECT
	library_file_id,
	library_id,
	codec_type,
	codec,
	CASE
		WHEN raw_layout <> '' THEN LOWER(CASE
			WHEN INSTR(raw_layout, '(') > 1 THEN SUBSTR(raw_layout, 1, INSTR(raw_layout, '(') - 1)
			ELSE raw_layout
		END)
		WHEN channels = 1 THEN 'mono'
		WHEN channels = 2 THEN 'stereo'
		WHEN channels = 6 THEN '5.1'
		WHEN channels = 8 THEN '7.1'
		WHEN channels > 0 THEN CAST(channels AS TEXT) || 'ch'
		ELSE 'unknown'
	END AS channel_layout,
	CASE
		WHEN base_language IN ('', 'und') THEN 'unknown'
		ELSE COALESCE((SELECT a.canonical FROM library_language_aliases AS a WHERE a.alias = base_language), base_language)
	END AS language
FROM (
	SELECT
		library_file_id, library_id, codec_type, codec, raw_layout, channels,
		-- NormalizeLang: lower-cased, trimmed, and cut at the first BCP 47 separator ("pt-BR" is "pt").
		CASE
			WHEN INSTR(raw_language, '-') > 0 THEN SUBSTR(raw_language, 1, INSTR(raw_language, '-') - 1)
			ELSE raw_language
		END AS base_language
	FROM library_file_tracks_raw);

INSERT OR IGNORE INTO library_file_facets (library_id, library_file_id, facet, value)
SELECT library_id, id, 'video_codec', COALESCE(video_codec, 'unknown') FROM library_files;

INSERT OR IGNORE INTO library_file_facets (library_id, library_file_id, facet, value)
SELECT library_id, id, 'resolution', COALESCE(resolution_class, 'unknown') FROM library_files;

INSERT OR IGNORE INTO library_file_facets (library_id, library_file_id, facet, value)
SELECT DISTINCT library_id, library_file_id, 'audio', codec || ' ' || channel_layout
FROM library_file_tracks WHERE codec_type = 'audio';

INSERT OR IGNORE INTO library_file_facets (library_id, library_file_id, facet, value)
SELECT DISTINCT library_id, library_file_id, 'audio_language', language
FROM library_file_tracks WHERE codec_type = 'audio';

INSERT OR IGNORE INTO library_file_facets (library_id, library_file_id, facet, value)
SELECT DISTINCT library_id, library_file_id, 'subtitle_language', language
FROM library_file_tracks WHERE codec_type = 'subtitle';

-- The plain-language track summaries the Files table shows, first three tracks then "+N more".
UPDATE library_files
SET audio_summary = (
	SELECT CASE WHEN COUNT(*) = 0 THEN NULL ELSE
		(SELECT GROUP_CONCAT(part, ', ') FROM (
			SELECT t.language || ' ' || t.codec || ' ' || t.channel_layout AS part
			FROM library_file_tracks AS t
			WHERE t.library_file_id = library_files.id AND t.codec_type = 'audio'
			LIMIT 3))
		|| CASE WHEN COUNT(*) > 3 THEN ' +' || CAST(COUNT(*) - 3 AS TEXT) || ' more' ELSE '' END
	END
	FROM library_file_tracks AS c WHERE c.library_file_id = library_files.id AND c.codec_type = 'audio'),
	subtitle_summary = (
	SELECT CASE WHEN COUNT(*) = 0 THEN NULL ELSE
		(SELECT GROUP_CONCAT(part, ', ') FROM (
			SELECT t.language AS part
			FROM library_file_tracks AS t
			WHERE t.library_file_id = library_files.id AND t.codec_type = 'subtitle'
			LIMIT 3))
		|| CASE WHEN COUNT(*) > 3 THEN ' +' || CAST(COUNT(*) - 3 AS TEXT) || ' more' ELSE '' END
	END
	FROM library_file_tracks AS c WHERE c.library_file_id = library_files.id AND c.codec_type = 'subtitle')
WHERE probe_json IS NOT NULL AND json_valid(probe_json);

-- The Problems view's grouping for rows classified before this migration: the two reasons a scan can state
-- without touching the file again are recognisable from the sentence it already recorded.
UPDATE library_files
SET problem_kind = CASE
		WHEN reason LIKE '%no video track%' THEN 'no_video'
		WHEN reason LIKE '%No audio track would remain%' THEN 'no_audio_left'
		ELSE 'unreadable'
	END
WHERE classification = 'cannot_process';

DROP VIEW library_file_tracks;
DROP VIEW library_file_tracks_raw;
DROP VIEW library_file_streams;
DROP VIEW library_file_video;
DROP TABLE library_language_aliases;
