-- Weir schema 0010 (revision 0045_keep_original_download): a library can keep the original download after cleaning.
--
-- On (the default, and what every existing library keeps on upgrade): after a successful pass Weir removes the
-- source from the watched folder, as it always has. Off: the source file, its folder and its sidecars stay where
-- the download client put them, so a torrent keeps seeding. Sonarr and Radarr only import a download the client
-- reports as completed, and qBittorrent reports a torrent whose files vanished as missingFiles, which they read as a
-- warning (Sonarr/Radarr develop Download/Clients/QBittorrent/QBittorrent.cs L281-283), so removing a seeding
-- torrent's files can stop the import it was cleaned for.
ALTER TABLE libraries ADD COLUMN remove_original_after_success BOOLEAN DEFAULT '1' NOT NULL;

-- The size and modification time of the source a successful pass cleaned, so a kept original is recognised on the
-- next scan and not cleaned again, while a new or replaced file at the same path (a different size or time) is.
-- Null for files processed before this, and for passes that failed.
ALTER TABLE files ADD COLUMN processed_source_size BIGINT;
ALTER TABLE files ADD COLUMN processed_source_mtime_ns BIGINT;
