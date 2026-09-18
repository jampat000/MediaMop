-- Weir schema 0009 (issue #578, revision 0044_drop_the_refiner_name): the module is gone,
-- so its name comes off the tables too.
--
-- ALTER TABLE ... RENAME TO would move the tables but leave every named constraint spelled
-- the old way, because those names live inside each table's own DDL text. So each table is
-- rebuilt under its new name with new constraint names. This file is generated from the
-- schema the shipped migrations actually produce, and verified against a populated database.
--
-- THE ORDER MATTERS, and not for the usual reason. SchemaMigrator.ApplyRange runs every
-- migration inside a transaction having set PRAGMA defer_foreign_keys=ON. A
-- PRAGMA foreign_keys=off inside a transaction is a no-op, and defer_foreign_keys defers
-- constraint *violations* - it does not stop an ON DELETE CASCADE firing. So a DROP really
-- does take the children's rows with it, transitively: dropping refiner_files would empty
-- library_files, and dropping library_files would empty library_file_facets.
-- Issue557MigrationTests and Issue568MigrationTests both caught this.
--
-- So every table in the closure of dependents is rebuilt and filled first, the originals
-- are dropped children-first, and the rebuilt ones then take their names back. At no point
-- does a cascade have a row left to delete.

-- Rebuilt because their name changes: refiner_file_logs -> file_logs, refiner_library_manager_links -> library_manager_links, refiner_operator_settings -> operator_settings, refiner_files -> files, refiner_jobs -> jobs, refiner_libraries -> libraries, refiner_rule_sets -> rule_sets
-- Rebuilt only because they point at one of those (directly or through another):
--   library_file_facets, library_folders, library_swaps, media_manager_handoffs, removed_tracks, library_files

-- 1. build every one of them, filled, while the originals still stand
-- refiner_rule_sets -> rule_sets
CREATE TABLE rule_sets (
	id INTEGER NOT NULL,
	name TEXT NOT NULL,
	primary_audio_lang TEXT DEFAULT '' NOT NULL,
	secondary_audio_lang TEXT DEFAULT '' NOT NULL,
	tertiary_audio_lang TEXT DEFAULT '' NOT NULL,
	default_audio_slot TEXT DEFAULT 'primary' NOT NULL,
	remove_commentary BOOLEAN DEFAULT '0' NOT NULL,
	subtitle_mode TEXT DEFAULT 'keep_all' NOT NULL,
	subtitle_langs_csv TEXT DEFAULT '' NOT NULL,
	preserve_forced_subs BOOLEAN DEFAULT '1' NOT NULL,
	preserve_default_subs BOOLEAN DEFAULT '1' NOT NULL,
	audio_preference_mode TEXT DEFAULT 'preferred_langs_quality' NOT NULL,
	audio_sorters_json TEXT DEFAULT '' NOT NULL,
	subtitle_sorters_json TEXT DEFAULT '' NOT NULL,
	keep_original_language BOOLEAN DEFAULT '0' NOT NULL,
	original_language_additional_csv TEXT DEFAULT '' NOT NULL,
	original_language_keep_only_first BOOLEAN DEFAULT '1' NOT NULL,
	original_language_first_if_none BOOLEAN DEFAULT '1' NOT NULL,
	original_language_treat_empty_as_original BOOLEAN DEFAULT '0' NOT NULL,
	remove_images BOOLEAN DEFAULT '0' NOT NULL,
	remove_attachments BOOLEAN DEFAULT '0' NOT NULL,
	remove_title BOOLEAN DEFAULT '0' NOT NULL,
	remove_language_tags BOOLEAN DEFAULT '0' NOT NULL,
	remove_other_metadata BOOLEAN DEFAULT '0' NOT NULL,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, remove_hearing_impaired_subs BOOLEAN DEFAULT '0' NOT NULL, audio_keep_mode TEXT DEFAULT 'single' NOT NULL, subtitle_max_per_language INTEGER DEFAULT '0' NOT NULL, subtitle_quality_strategy TEXT DEFAULT 'text_first' NOT NULL, standardize_track_names BOOLEAN DEFAULT '0' NOT NULL, track_name_template TEXT DEFAULT '{language}{variant} {channels} {codec}' NOT NULL, track_name_override_forced TEXT DEFAULT '{language} {flags}' NOT NULL, track_name_override_hearing_impaired TEXT DEFAULT '{language} {flags}' NOT NULL, track_name_override_commentary TEXT DEFAULT '{language} {flags}' NOT NULL, track_name_override_audio_description TEXT DEFAULT '{language} {flags}' NOT NULL, clear_video_track_names BOOLEAN DEFAULT '0' NOT NULL, remove_chapters BOOLEAN DEFAULT '0' NOT NULL,
	CONSTRAINT pk_rule_sets PRIMARY KEY (id),
	CONSTRAINT uq_rule_sets_name UNIQUE (name)
);
INSERT INTO rule_sets ("id", "name", "primary_audio_lang", "secondary_audio_lang", "tertiary_audio_lang", "default_audio_slot", "remove_commentary", "subtitle_mode", "subtitle_langs_csv", "preserve_forced_subs", "preserve_default_subs", "audio_preference_mode", "audio_sorters_json", "subtitle_sorters_json", "keep_original_language", "original_language_additional_csv", "original_language_keep_only_first", "original_language_first_if_none", "original_language_treat_empty_as_original", "remove_images", "remove_attachments", "remove_title", "remove_language_tags", "remove_other_metadata", "created_at", "updated_at", "remove_hearing_impaired_subs", "audio_keep_mode", "subtitle_max_per_language", "subtitle_quality_strategy", "standardize_track_names", "track_name_template", "track_name_override_forced", "track_name_override_hearing_impaired", "track_name_override_commentary", "track_name_override_audio_description", "clear_video_track_names", "remove_chapters") SELECT "id", "name", "primary_audio_lang", "secondary_audio_lang", "tertiary_audio_lang", "default_audio_slot", "remove_commentary", "subtitle_mode", "subtitle_langs_csv", "preserve_forced_subs", "preserve_default_subs", "audio_preference_mode", "audio_sorters_json", "subtitle_sorters_json", "keep_original_language", "original_language_additional_csv", "original_language_keep_only_first", "original_language_first_if_none", "original_language_treat_empty_as_original", "remove_images", "remove_attachments", "remove_title", "remove_language_tags", "remove_other_metadata", "created_at", "updated_at", "remove_hearing_impaired_subs", "audio_keep_mode", "subtitle_max_per_language", "subtitle_quality_strategy", "standardize_track_names", "track_name_template", "track_name_override_forced", "track_name_override_hearing_impaired", "track_name_override_commentary", "track_name_override_audio_description", "clear_video_track_names", "remove_chapters" FROM refiner_rule_sets;
-- refiner_libraries -> libraries
CREATE TABLE libraries (
	id INTEGER NOT NULL,
	name TEXT NOT NULL,
	enabled BOOLEAN DEFAULT '1' NOT NULL,
	media_type TEXT DEFAULT 'movie' NOT NULL,
	display_order INTEGER DEFAULT '0' NOT NULL,
	watched_folder TEXT DEFAULT '' NOT NULL,
	work_folder TEXT DEFAULT '' NOT NULL,
	output_folder TEXT DEFAULT '' NOT NULL,
	media_extensions_csv TEXT DEFAULT '' NOT NULL,
	exclude_markers_csv TEXT DEFAULT '' NOT NULL,
	include_patterns_csv TEXT DEFAULT '' NOT NULL,
	exclude_patterns_csv TEXT DEFAULT '' NOT NULL,
	min_file_size_mb INTEGER DEFAULT '0' NOT NULL,
	max_file_size_mb INTEGER DEFAULT '0' NOT NULL,
	rejected_file_action TEXT DEFAULT 'leave' NOT NULL,
	min_file_age_seconds INTEGER DEFAULT '60' NOT NULL,
	created_after DATETIME,
	created_before DATETIME,
	modified_after DATETIME,
	modified_before DATETIME,
	exclude_hidden BOOLEAN DEFAULT '1' NOT NULL,
	top_level_only BOOLEAN DEFAULT '0' NOT NULL,
	sidecar_patterns_csv TEXT DEFAULT '.srt,.ass,.ssa,.sub,.idx,.vtt,.nfo,.jpg,.png' NOT NULL,
	preserve_original_timestamps BOOLEAN DEFAULT '0' NOT NULL,
	output_collision_policy TEXT DEFAULT 'replace' NOT NULL,
	hardware_decode_mode TEXT DEFAULT 'off' NOT NULL,
	hardware_device TEXT DEFAULT '' NOT NULL,
	hardware_disabled_vendors_csv TEXT DEFAULT '' NOT NULL,
	ffmpeg_strictness TEXT DEFAULT 'normal' NOT NULL,
	scan_interval_seconds INTEGER DEFAULT '300' NOT NULL,
	hold_minutes INTEGER DEFAULT '0' NOT NULL,
	file_detection_interval_seconds INTEGER DEFAULT '30' NOT NULL,
	ignore_size_changes BOOLEAN DEFAULT '0' NOT NULL,
	file_system_events_enabled BOOLEAN DEFAULT '1' NOT NULL,
	skip_access_tests BOOLEAN DEFAULT '0' NOT NULL,
	schedule_enabled BOOLEAN DEFAULT '1' NOT NULL,
	schedule_hours_limited BOOLEAN DEFAULT '0' NOT NULL,
	schedule_days TEXT DEFAULT '' NOT NULL,
	schedule_grid TEXT DEFAULT '' NOT NULL,
	schedule_start TEXT DEFAULT '00:00' NOT NULL,
	schedule_end TEXT DEFAULT '23:59' NOT NULL,
	max_attempts INTEGER DEFAULT '3' NOT NULL,
	retry_backoff_seconds INTEGER DEFAULT '300' NOT NULL,
	retry_execution_failures BOOLEAN DEFAULT '1' NOT NULL,
	retry_preflight_failures BOOLEAN DEFAULT '0' NOT NULL,
	failure_policy TEXT DEFAULT 'pass_through' NOT NULL,
	max_concurrent_files INTEGER DEFAULT '1' NOT NULL,
	priority INTEGER DEFAULT '0' NOT NULL,
	rule_set_id INTEGER,
	discovered_from_connection_id INTEGER,
	discovered_library_key TEXT,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, library_schedule_enabled BOOLEAN DEFAULT '0' NOT NULL, clean_hardlinked_files BOOLEAN DEFAULT '0' NOT NULL, skip_if_manager_would_redownload BOOLEAN DEFAULT '1' NOT NULL, remux_writer TEXT DEFAULT 'best' NOT NULL, rewrite_with_ffmpeg BOOLEAN DEFAULT '1' NOT NULL,
	CONSTRAINT pk_libraries PRIMARY KEY (id),
	CONSTRAINT uq_libraries_name UNIQUE (name),
	CONSTRAINT fk_libraries_rule_sets_rule_set_id FOREIGN KEY(rule_set_id) REFERENCES rule_sets (id) ON DELETE RESTRICT,
	CONSTRAINT fk_libraries_media_manager_connections_discovered_from_connection_id FOREIGN KEY(discovered_from_connection_id) REFERENCES media_manager_connections (id) ON DELETE SET NULL
);
INSERT INTO libraries ("id", "name", "enabled", "media_type", "display_order", "watched_folder", "work_folder", "output_folder", "media_extensions_csv", "exclude_markers_csv", "include_patterns_csv", "exclude_patterns_csv", "min_file_size_mb", "max_file_size_mb", "rejected_file_action", "min_file_age_seconds", "created_after", "created_before", "modified_after", "modified_before", "exclude_hidden", "top_level_only", "sidecar_patterns_csv", "preserve_original_timestamps", "output_collision_policy", "hardware_decode_mode", "hardware_device", "hardware_disabled_vendors_csv", "ffmpeg_strictness", "scan_interval_seconds", "hold_minutes", "file_detection_interval_seconds", "ignore_size_changes", "file_system_events_enabled", "skip_access_tests", "schedule_enabled", "schedule_hours_limited", "schedule_days", "schedule_grid", "schedule_start", "schedule_end", "max_attempts", "retry_backoff_seconds", "retry_execution_failures", "retry_preflight_failures", "failure_policy", "max_concurrent_files", "priority", "rule_set_id", "discovered_from_connection_id", "discovered_library_key", "created_at", "updated_at", "library_schedule_enabled", "clean_hardlinked_files", "skip_if_manager_would_redownload", "remux_writer", "rewrite_with_ffmpeg") SELECT "id", "name", "enabled", "media_type", "display_order", "watched_folder", "work_folder", "output_folder", "media_extensions_csv", "exclude_markers_csv", "include_patterns_csv", "exclude_patterns_csv", "min_file_size_mb", "max_file_size_mb", "rejected_file_action", "min_file_age_seconds", "created_after", "created_before", "modified_after", "modified_before", "exclude_hidden", "top_level_only", "sidecar_patterns_csv", "preserve_original_timestamps", "output_collision_policy", "hardware_decode_mode", "hardware_device", "hardware_disabled_vendors_csv", "ffmpeg_strictness", "scan_interval_seconds", "hold_minutes", "file_detection_interval_seconds", "ignore_size_changes", "file_system_events_enabled", "skip_access_tests", "schedule_enabled", "schedule_hours_limited", "schedule_days", "schedule_grid", "schedule_start", "schedule_end", "max_attempts", "retry_backoff_seconds", "retry_execution_failures", "retry_preflight_failures", "failure_policy", "max_concurrent_files", "priority", "rule_set_id", "discovered_from_connection_id", "discovered_library_key", "created_at", "updated_at", "library_schedule_enabled", "clean_hardlinked_files", "skip_if_manager_would_redownload", "remux_writer", "rewrite_with_ffmpeg" FROM refiner_libraries;
-- refiner_jobs -> jobs
CREATE TABLE jobs (
	id INTEGER NOT NULL,
	dedupe_key VARCHAR(512) NOT NULL,
	job_kind VARCHAR(64) NOT NULL,
	payload_json TEXT,
	status VARCHAR(32) DEFAULT 'pending' NOT NULL,
	lease_owner VARCHAR(200),
	lease_expires_at DATETIME,
	attempt_count INTEGER DEFAULT 0 NOT NULL,
	max_attempts INTEGER DEFAULT 3 NOT NULL,
	last_error TEXT,
	not_before DATETIME,
	runner_cost INTEGER DEFAULT '0' NOT NULL,
	priority INTEGER DEFAULT '0' NOT NULL,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_jobs PRIMARY KEY (id),
	CONSTRAINT uq_jobs_dedupe_key UNIQUE (dedupe_key)
);
INSERT INTO jobs ("id", "dedupe_key", "job_kind", "payload_json", "status", "lease_owner", "lease_expires_at", "attempt_count", "max_attempts", "last_error", "not_before", "runner_cost", "priority", "created_at", "updated_at") SELECT "id", "dedupe_key", "job_kind", "payload_json", "status", "lease_owner", "lease_expires_at", "attempt_count", "max_attempts", "last_error", "not_before", "runner_cost", "priority", "created_at", "updated_at" FROM refiner_jobs;
-- refiner_files -> files
CREATE TABLE files (
	id INTEGER NOT NULL,
	library_id INTEGER NOT NULL,
	relative_path TEXT NOT NULL,
	status TEXT DEFAULT 'unprocessed' NOT NULL,
	status_reason TEXT DEFAULT '' NOT NULL,
	blocked_by_connection TEXT,
	size_bytes BIGINT DEFAULT '0' NOT NULL,
	video_width INTEGER,
	video_height INTEGER,
	video_codec TEXT,
	audio_track_count INTEGER,
	subtitle_track_count INTEGER,
	duration_seconds FLOAT,
	audio_codecs TEXT,
	video_bit_depth INTEGER,
	size_changed_at DATETIME,
	hold_until DATETIME,
	failure_class TEXT,
	failure_attempts INTEGER DEFAULT '0' NOT NULL,
	next_retry_at DATETIME,
	output_collision_policy TEXT,
	output_collision_action TEXT,
	output_collision_reason TEXT,
	hardware_method TEXT,
	hardware_fell_back_to_software BOOLEAN DEFAULT '0' NOT NULL,
	hardware_reason TEXT,
	last_seen_at DATETIME,
	last_attempt_at DATETIME,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_files PRIMARY KEY (id),
	CONSTRAINT uq_files_library_path UNIQUE (library_id, relative_path),
	CONSTRAINT fk_files_libraries_library_id FOREIGN KEY(library_id) REFERENCES libraries (id) ON DELETE CASCADE
);
INSERT INTO files ("id", "library_id", "relative_path", "status", "status_reason", "blocked_by_connection", "size_bytes", "video_width", "video_height", "video_codec", "audio_track_count", "subtitle_track_count", "duration_seconds", "audio_codecs", "video_bit_depth", "size_changed_at", "hold_until", "failure_class", "failure_attempts", "next_retry_at", "output_collision_policy", "output_collision_action", "output_collision_reason", "hardware_method", "hardware_fell_back_to_software", "hardware_reason", "last_seen_at", "last_attempt_at", "created_at", "updated_at") SELECT "id", "library_id", "relative_path", "status", "status_reason", "blocked_by_connection", "size_bytes", "video_width", "video_height", "video_codec", "audio_track_count", "subtitle_track_count", "duration_seconds", "audio_codecs", "video_bit_depth", "size_changed_at", "hold_until", "failure_class", "failure_attempts", "next_retry_at", "output_collision_policy", "output_collision_action", "output_collision_reason", "hardware_method", "hardware_fell_back_to_software", "hardware_reason", "last_seen_at", "last_attempt_at", "created_at", "updated_at" FROM refiner_files;
-- library_files -> library_files__new
CREATE TABLE library_files__new (
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
	scanned_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, video_codec TEXT, video_height INTEGER, resolution_class TEXT, audio_track_count INTEGER DEFAULT '0' NOT NULL, subtitle_track_count INTEGER DEFAULT '0' NOT NULL, audio_summary TEXT, subtitle_summary TEXT, link_count INTEGER, problem_kind TEXT,
	CONSTRAINT pk_library_files PRIMARY KEY (id),
	CONSTRAINT uq_library_files_library_id_path UNIQUE (library_id, path),
	CONSTRAINT fk_library_files_libraries_library_id FOREIGN KEY(library_id) REFERENCES libraries (id) ON DELETE CASCADE,
	CONSTRAINT fk_library_files_media_manager_connections_manager_connection_id FOREIGN KEY(manager_connection_id) REFERENCES media_manager_connections (id) ON DELETE SET NULL
);
INSERT INTO library_files__new ("id", "library_id", "path", "size_bytes", "mtime", "classification", "summary", "reason", "removed_audio_tracks", "removed_subtitle_tracks", "estimated_bytes_saved", "manager_kind", "manager_title", "manager_connection_id", "manager_title_id", "manager_file_id", "manager_quality_profile_id", "probe_json", "scanned_at", "video_codec", "video_height", "resolution_class", "audio_track_count", "subtitle_track_count", "audio_summary", "subtitle_summary", "link_count", "problem_kind") SELECT "id", "library_id", "path", "size_bytes", "mtime", "classification", "summary", "reason", "removed_audio_tracks", "removed_subtitle_tracks", "estimated_bytes_saved", "manager_kind", "manager_title", "manager_connection_id", "manager_title_id", "manager_file_id", "manager_quality_profile_id", "probe_json", "scanned_at", "video_codec", "video_height", "resolution_class", "audio_track_count", "subtitle_track_count", "audio_summary", "subtitle_summary", "link_count", "problem_kind" FROM library_files;
-- removed_tracks -> removed_tracks__new
CREATE TABLE removed_tracks__new (
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
	CONSTRAINT fk_removed_tracks_libraries_library_id FOREIGN KEY(library_id) REFERENCES libraries (id) ON DELETE SET NULL
);
INSERT INTO removed_tracks__new ("id", "library_id", "relative_path", "language", "track_type", "codec", "variant", "reason", "recorded_at") SELECT "id", "library_id", "relative_path", "language", "track_type", "codec", "variant", "reason", "recorded_at" FROM removed_tracks;
-- refiner_operator_settings -> operator_settings
CREATE TABLE operator_settings (
	id INTEGER NOT NULL,
	max_concurrent_files INTEGER DEFAULT '1' NOT NULL,
	runner_capacity INTEGER DEFAULT '4' NOT NULL,
	runner_cost_sd INTEGER DEFAULT '0' NOT NULL,
	runner_cost_720p INTEGER DEFAULT '0' NOT NULL,
	runner_cost_1080p INTEGER DEFAULT '1' NOT NULL,
	runner_cost_4k INTEGER DEFAULT '1' NOT NULL,
	runner_cost_undetermined INTEGER DEFAULT '0' NOT NULL,
	work_temp_stale_sweep_enabled BOOLEAN DEFAULT '1' NOT NULL,
	failure_cleanup_enabled BOOLEAN DEFAULT '0' NOT NULL,
	keep_failed_work_files BOOLEAN DEFAULT '0' NOT NULL,
	file_log_retention_days INTEGER DEFAULT '90' NOT NULL,
	verbose_detection_logging BOOLEAN DEFAULT '0' NOT NULL,
	min_file_age_seconds INTEGER DEFAULT '60' NOT NULL,
	min_input_file_size_mb INTEGER DEFAULT '50' NOT NULL,
	minimum_free_disk_space_mb INTEGER DEFAULT '5120' NOT NULL,
	movie_schedule_enabled INTEGER DEFAULT '1' NOT NULL,
	movie_schedule_hours_limited INTEGER DEFAULT '0' NOT NULL,
	movie_schedule_days TEXT DEFAULT '' NOT NULL,
	movie_schedule_start TEXT DEFAULT '00:00' NOT NULL,
	movie_schedule_end TEXT DEFAULT '23:59' NOT NULL,
	tv_schedule_enabled INTEGER DEFAULT '1' NOT NULL,
	tv_schedule_hours_limited INTEGER DEFAULT '0' NOT NULL,
	tv_schedule_days TEXT DEFAULT '' NOT NULL,
	tv_schedule_start TEXT DEFAULT '00:00' NOT NULL,
	tv_schedule_end TEXT DEFAULT '23:59' NOT NULL,
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_operator_settings PRIMARY KEY (id),
	CONSTRAINT ck_operator_settings_ck_operator_settings_singleton CHECK (id = 1)
);
INSERT INTO operator_settings ("id", "max_concurrent_files", "runner_capacity", "runner_cost_sd", "runner_cost_720p", "runner_cost_1080p", "runner_cost_4k", "runner_cost_undetermined", "work_temp_stale_sweep_enabled", "failure_cleanup_enabled", "keep_failed_work_files", "file_log_retention_days", "verbose_detection_logging", "min_file_age_seconds", "min_input_file_size_mb", "minimum_free_disk_space_mb", "movie_schedule_enabled", "movie_schedule_hours_limited", "movie_schedule_days", "movie_schedule_start", "movie_schedule_end", "tv_schedule_enabled", "tv_schedule_hours_limited", "tv_schedule_days", "tv_schedule_start", "tv_schedule_end", "updated_at") SELECT "id", "max_concurrent_files", "runner_capacity", "runner_cost_sd", "runner_cost_720p", "runner_cost_1080p", "runner_cost_4k", "runner_cost_undetermined", "work_temp_stale_sweep_enabled", "failure_cleanup_enabled", "keep_failed_work_files", "file_log_retention_days", "verbose_detection_logging", "min_file_age_seconds", "refiner_min_input_file_size_mb", "minimum_free_disk_space_mb", "movie_schedule_enabled", "movie_schedule_hours_limited", "movie_schedule_days", "movie_schedule_start", "movie_schedule_end", "tv_schedule_enabled", "tv_schedule_hours_limited", "tv_schedule_days", "tv_schedule_start", "tv_schedule_end", "updated_at" FROM refiner_operator_settings;
-- refiner_library_manager_links -> library_manager_links
CREATE TABLE library_manager_links (
	id INTEGER NOT NULL,
	library_id INTEGER NOT NULL,
	connection_id INTEGER NOT NULL,
	CONSTRAINT pk_library_manager_links PRIMARY KEY (id),
	CONSTRAINT uq_library_manager_links_pair UNIQUE (library_id, connection_id),
	CONSTRAINT fk_library_manager_links_libraries_library_id FOREIGN KEY(library_id) REFERENCES libraries (id) ON DELETE CASCADE,
	CONSTRAINT fk_library_manager_links_media_manager_connections_connection_id FOREIGN KEY(connection_id) REFERENCES media_manager_connections (id) ON DELETE CASCADE
);
INSERT INTO library_manager_links ("id", "library_id", "connection_id") SELECT "id", "library_id", "connection_id" FROM refiner_library_manager_links;
-- refiner_file_logs -> file_logs
CREATE TABLE file_logs (
	id INTEGER NOT NULL,
	file_id INTEGER,
	library_id INTEGER,
	relative_path TEXT NOT NULL,
	library_name TEXT DEFAULT '' NOT NULL,
	outcome TEXT DEFAULT '' NOT NULL,
	title TEXT DEFAULT '' NOT NULL,
	detail_json TEXT DEFAULT '{}' NOT NULL,
	recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_file_logs PRIMARY KEY (id),
	CONSTRAINT fk_file_logs_files_file_id FOREIGN KEY(file_id) REFERENCES files (id) ON DELETE SET NULL,
	CONSTRAINT fk_file_logs_libraries_library_id FOREIGN KEY(library_id) REFERENCES libraries (id) ON DELETE SET NULL
);
INSERT INTO file_logs ("id", "file_id", "library_id", "relative_path", "library_name", "outcome", "title", "detail_json", "recorded_at") SELECT "id", "file_id", "library_id", "relative_path", "library_name", "outcome", "title", "detail_json", "recorded_at" FROM refiner_file_logs;
-- media_manager_handoffs -> media_manager_handoffs__new
CREATE TABLE media_manager_handoffs__new (
	id INTEGER NOT NULL,
	source_key TEXT NOT NULL,
	handoff_id TEXT NOT NULL,
	library_id INTEGER,
	relative_path TEXT NOT NULL,
	state TEXT DEFAULT 'queued' NOT NULL,
	output_path TEXT,
	message TEXT,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	last_changed_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_media_manager_handoffs PRIMARY KEY (id),
	CONSTRAINT uq_media_manager_handoffs_source_id UNIQUE (source_key, handoff_id),
	CONSTRAINT fk_media_manager_handoffs_libraries_library_id FOREIGN KEY(library_id) REFERENCES libraries (id) ON DELETE SET NULL
);
INSERT INTO media_manager_handoffs__new ("id", "source_key", "handoff_id", "library_id", "relative_path", "state", "output_path", "message", "created_at", "last_changed_at") SELECT "id", "source_key", "handoff_id", "library_id", "relative_path", "state", "output_path", "message", "created_at", "last_changed_at" FROM media_manager_handoffs;
-- library_swaps -> library_swaps__new
CREATE TABLE library_swaps__new (
	job_id INTEGER NOT NULL,
	state TEXT NOT NULL,
	original_path TEXT NOT NULL,
	temp_path TEXT NOT NULL,
	backup_path TEXT NOT NULL,
	committed BOOLEAN DEFAULT '0' NOT NULL,
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_library_swaps PRIMARY KEY (job_id),
	CONSTRAINT fk_library_swaps_jobs_job_id FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE
);
INSERT INTO library_swaps__new ("job_id", "state", "original_path", "temp_path", "backup_path", "committed", "updated_at") SELECT "job_id", "state", "original_path", "temp_path", "backup_path", "committed", "updated_at" FROM library_swaps;
-- library_folders -> library_folders__new
CREATE TABLE library_folders__new (
	id INTEGER NOT NULL,
	library_id INTEGER NOT NULL,
	folder TEXT NOT NULL,
	position INTEGER DEFAULT '0' NOT NULL,
	CONSTRAINT pk_library_folders PRIMARY KEY (id),
	CONSTRAINT uq_library_folders_library_id_folder UNIQUE (library_id, folder),
	CONSTRAINT fk_library_folders_libraries_library_id FOREIGN KEY(library_id) REFERENCES libraries (id) ON DELETE CASCADE
);
INSERT INTO library_folders__new ("id", "library_id", "folder", "position") SELECT "id", "library_id", "folder", "position" FROM library_folders;
-- library_file_facets -> library_file_facets__new
CREATE TABLE library_file_facets__new (
	id INTEGER NOT NULL,
	library_id INTEGER NOT NULL,
	library_file_id INTEGER NOT NULL,
	facet TEXT NOT NULL,
	value TEXT NOT NULL,
	CONSTRAINT pk_library_file_facets PRIMARY KEY (id),
	CONSTRAINT uq_library_file_facets_file_facet_value UNIQUE (library_file_id, facet, value),
	CONSTRAINT fk_library_file_facets_library_files_library_file_id FOREIGN KEY(library_file_id) REFERENCES library_files (id) ON DELETE CASCADE,
	CONSTRAINT fk_library_file_facets_libraries_library_id FOREIGN KEY(library_id) REFERENCES libraries (id) ON DELETE CASCADE
);
INSERT INTO library_file_facets__new ("id", "library_id", "library_file_id", "facet", "value") SELECT "id", "library_id", "library_file_id", "facet", "value" FROM library_file_facets;

-- 2. drop the originals, children first, so no cascade has anything to take
DROP TABLE library_file_facets;
DROP TABLE library_folders;
DROP TABLE library_swaps;
DROP TABLE media_manager_handoffs;
DROP TABLE refiner_file_logs;
DROP TABLE refiner_library_manager_links;
DROP TABLE refiner_operator_settings;
DROP TABLE removed_tracks;
DROP TABLE library_files;
DROP TABLE refiner_files;
DROP TABLE refiner_jobs;
DROP TABLE refiner_libraries;
DROP TABLE refiner_rule_sets;

-- 3. the ones that keep their names take them back
ALTER TABLE library_file_facets__new RENAME TO library_file_facets;
ALTER TABLE library_folders__new RENAME TO library_folders;
ALTER TABLE library_swaps__new RENAME TO library_swaps;
ALTER TABLE media_manager_handoffs__new RENAME TO media_manager_handoffs;
ALTER TABLE removed_tracks__new RENAME TO removed_tracks;
ALTER TABLE library_files__new RENAME TO library_files;

-- 4. indexes, which went with the tables they sat on
CREATE INDEX ix_library_file_facets_library_file_id ON library_file_facets (library_file_id);
CREATE INDEX ix_library_file_facets_library_id_facet_value ON library_file_facets (library_id, facet, value);
CREATE INDEX ix_library_files_library_id ON library_files (library_id);
CREATE INDEX ix_library_files_library_id_classification ON library_files (library_id, classification);
CREATE INDEX ix_library_files_library_id_problem_kind ON library_files (library_id, problem_kind);
CREATE INDEX ix_library_files_library_id_resolution_class ON library_files (library_id, resolution_class);
CREATE INDEX ix_library_files_library_id_size_bytes ON library_files (library_id, size_bytes);
CREATE INDEX ix_library_files_library_id_video_codec ON library_files (library_id, video_codec);
CREATE INDEX ix_library_folders_library_id ON library_folders (library_id);
CREATE INDEX ix_file_logs_file ON file_logs (file_id);
CREATE INDEX ix_file_logs_path ON file_logs (relative_path);
CREATE INDEX ix_file_logs_recorded_at ON file_logs (recorded_at);
CREATE INDEX ix_files_library_status ON files (library_id, status);
CREATE INDEX ix_files_status ON files (status);
CREATE INDEX ix_jobs_status_id ON jobs (status, id);
CREATE INDEX ix_removed_tracks_library_id_relative_path ON removed_tracks (library_id, relative_path);

-- 5. the strings the rows themselves carry. A queued job whose kind still said refiner
--    would never match a handler again, and an activity entry would drop out of its own
--    filter.
UPDATE jobs SET job_kind = 'processing.' || substr(job_kind, 9) WHERE job_kind LIKE 'refiner.%';
UPDATE jobs SET dedupe_key = 'processing.' || substr(dedupe_key, 9) WHERE dedupe_key LIKE 'refiner.%';
UPDATE activity_events SET event_type = 'processing.' || substr(event_type, 9) WHERE event_type LIKE 'refiner.%';
