Revision scripts live in **`versions/`**.

- **`0001_initial_auth`** — `users`, `user_sessions` (SQLite).
- **`0002_activity_events`** — activity feed table.

Run from **`apps/backend`** with `PYTHONPATH=src`. The database URL is taken from **`MediaMopSettings.load()`** (same as the API: **`MEDIAMOP_HOME`**, **`MEDIAMOP_DB_PATH`**, etc.).
