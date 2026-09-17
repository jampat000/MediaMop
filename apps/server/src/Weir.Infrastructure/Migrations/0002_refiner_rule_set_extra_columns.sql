-- Weir schema 0002 (issue #557, revision 0037_refiner_rule_set_extra_columns): give issues
-- #495/#497/#498's rule-set fields real columns instead of the "rule_extras_v1" envelope packed
-- into subtitle_sorters_json (Weir.Core.Refiner.RuleSetRuleExtras). Data is copied out of the
-- envelope, then subtitle_sorters_json is put back to holding only the plain sorter array it held
-- before the envelope existed.

ALTER TABLE refiner_rule_sets ADD COLUMN remove_hearing_impaired_subs BOOLEAN DEFAULT '0' NOT NULL;
ALTER TABLE refiner_rule_sets ADD COLUMN audio_keep_mode TEXT DEFAULT 'single' NOT NULL;
ALTER TABLE refiner_rule_sets ADD COLUMN subtitle_max_per_language INTEGER DEFAULT '0' NOT NULL;
ALTER TABLE refiner_rule_sets ADD COLUMN subtitle_quality_strategy TEXT DEFAULT 'text_first' NOT NULL;
ALTER TABLE refiner_rule_sets ADD COLUMN standardize_track_names BOOLEAN DEFAULT '0' NOT NULL;
ALTER TABLE refiner_rule_sets ADD COLUMN track_name_template TEXT DEFAULT '{language}{variant} {channels} {codec}' NOT NULL;
ALTER TABLE refiner_rule_sets ADD COLUMN track_name_override_forced TEXT DEFAULT '{language} {flags}' NOT NULL;
ALTER TABLE refiner_rule_sets ADD COLUMN track_name_override_hearing_impaired TEXT DEFAULT '{language} {flags}' NOT NULL;
ALTER TABLE refiner_rule_sets ADD COLUMN track_name_override_commentary TEXT DEFAULT '{language} {flags}' NOT NULL;
ALTER TABLE refiner_rule_sets ADD COLUMN track_name_override_audio_description TEXT DEFAULT '{language} {flags}' NOT NULL;
ALTER TABLE refiner_rule_sets ADD COLUMN clear_video_track_names BOOLEAN DEFAULT '0' NOT NULL;
ALTER TABLE refiner_rule_sets ADD COLUMN remove_chapters BOOLEAN DEFAULT '0' NOT NULL;

-- Copy every existing row's envelope (when subtitle_sorters_json is the
-- {"sorters": [...], "rule_extras_v1": {...}} object RuleSetRuleExtras.Encode wrote) into the new
-- columns. A row whose column is empty, or a bare JSON array (the shape this column has always had
-- when no envelope was ever written), is left at the defaults just applied above — exactly what
-- RuleSetRuleExtras.Decode already treats a legacy value as.
UPDATE refiner_rule_sets
SET
	remove_hearing_impaired_subs = COALESCE(json_extract(subtitle_sorters_json, '$.rule_extras_v1.remove_hearing_impaired_subs'), 0),
	audio_keep_mode = COALESCE(json_extract(subtitle_sorters_json, '$.rule_extras_v1.audio_keep_mode'), 'single'),
	subtitle_max_per_language = COALESCE(json_extract(subtitle_sorters_json, '$.rule_extras_v1.subtitle_max_per_language'), 0),
	subtitle_quality_strategy = COALESCE(json_extract(subtitle_sorters_json, '$.rule_extras_v1.subtitle_quality_strategy'), 'text_first'),
	standardize_track_names = COALESCE(json_extract(subtitle_sorters_json, '$.rule_extras_v1.standardize_track_names'), 0),
	track_name_template = COALESCE(json_extract(subtitle_sorters_json, '$.rule_extras_v1.track_name_template'), '{language}{variant} {channels} {codec}'),
	track_name_override_forced = COALESCE(json_extract(subtitle_sorters_json, '$.rule_extras_v1.track_name_overrides.forced'), '{language} {flags}'),
	track_name_override_hearing_impaired = COALESCE(json_extract(subtitle_sorters_json, '$.rule_extras_v1.track_name_overrides.hearing_impaired'), '{language} {flags}'),
	track_name_override_commentary = COALESCE(json_extract(subtitle_sorters_json, '$.rule_extras_v1.track_name_overrides.commentary'), '{language} {flags}'),
	track_name_override_audio_description = COALESCE(json_extract(subtitle_sorters_json, '$.rule_extras_v1.track_name_overrides.audio_description'), '{language} {flags}'),
	clear_video_track_names = COALESCE(json_extract(subtitle_sorters_json, '$.rule_extras_v1.clear_video_track_names'), 0),
	remove_chapters = COALESCE(json_extract(subtitle_sorters_json, '$.rule_extras_v1.remove_chapters'), 0)
WHERE json_valid(subtitle_sorters_json) AND json_type(subtitle_sorters_json) = 'object';

-- Put subtitle_sorters_json back to the plain sorter array (or empty) it held before #495/#497/#498
-- packed the envelope into it.
UPDATE refiner_rule_sets
SET subtitle_sorters_json = COALESCE(json_extract(subtitle_sorters_json, '$.sorters'), '')
WHERE json_valid(subtitle_sorters_json) AND json_type(subtitle_sorters_json) = 'object';
