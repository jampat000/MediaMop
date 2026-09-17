-- Weir schema 0008 (issue #548, revision 0043_remux_writer): which tool writes a library's output.
--
-- "best" (the default) means the best tool for each container: mkvmerge for Matroska when it is installed,
-- ffmpeg for everything else and whenever mkvmerge declines a file. "ffmpeg" means ffmpeg writes everything,
-- which is what every Weir before this did.
--
-- Existing libraries take the same default as new ones rather than being pinned to "ffmpeg" on upgrade.
-- That is safe because a write that fails to run or fails #500's validation is rewritten by ffmpeg and
-- validated again (rewrite_with_ffmpeg below), so the preferred writer can only match or beat ffmpeg alone.
ALTER TABLE refiner_libraries ADD COLUMN remux_writer TEXT DEFAULT 'best' NOT NULL;

-- The safety net that makes the default above defensible. Off means a file the preferred writer cannot
-- write fails instead of being written by ffmpeg, which is only wanted when someone is deliberately
-- measuring one writer on its own.
ALTER TABLE refiner_libraries ADD COLUMN rewrite_with_ffmpeg BOOLEAN DEFAULT '1' NOT NULL;
