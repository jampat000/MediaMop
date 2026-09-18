# Processing and media-manager coverage

Processing's basic watched-folder remux is standalone. After a file has passed the
local age, settling, access, schedule, and lifecycle checks, it can be processed
without Radarr, Sonarr, Deluno, or another manager.

| Workflow | Standalone | Radarr/Sonarr | Deluno | Native hand-off |
| --- | --- | --- | --- | --- |
| Watched-folder remux | Supported; local safety gates apply | Supported | Supported | Supported |
| Upstream import protection | Reduced safety: no upstream import check | Enhanced when the connection answers | Enhanced when the connection answers | Depends on the hand-off signal |
| Library discovery/sync | Manual libraries | Optional convenience | Optional convenience | Optional convenience |
| Destructive cleanup requiring manager truth | Safely held until Weir can confirm | Available when the manager answers | Available when the manager answers | Depends on the hand-off contract |
| Callback/hand-off | Not required | Integration-specific | Integration-specific | Supported where configured |

The library screen uses three coverage states:

- **Connected** — the linked connection passed its latest test.
- **No upstream signal** — no manager is linked, or a linked manager has not yet
  returned a successful signal. This does not mean that its queue is empty.
- **Unreachable** — a linked manager failed its latest connection test. Local
  remux remains possible, but manager-truth-dependent cleanup is held.

Connect or repair a manager from Settings → Media managers. A manually created
library remains valid and is never deleted or disabled merely because it has no
manager link.

## How each manager picks up Weir's output

- **Deluno** hands each finished download to Weir over its API and imports the
  cleaned file itself. A library only needs Deluno's folders: the one its
  downloads arrive in as the watched folder (a hand-off must sit inside it), and
  its processed-output folder as the output folder. The library editor reads
  both from Deluno's manifest and offers to fill them in.
- **Sonarr and Radarr** are set up by hand, the way FileFlows documents it: the
  download client finishes into Weir's watched folder, and a remote path mapping
  in Sonarr/Radarr (Settings → Download Clients → Remote Path Mappings) maps that
  folder to Weir's output folder, so Completed Download Handling only ever looks
  at cleaned files. Weir writes each output under the same relative path, name
  and extension as the download, and publishes it in one step. With a torrent
  client, turn off the library's "After cleaning, remove the original download":
  Sonarr/Radarr only import a download the client reports as completed, and a
  torrent whose files Weir removed reports missing files instead. Kept originals
  are recognised by size and modification time and never cleaned twice. The library editor
  shows the exact Host, Remote Path and Local Path, and checks them against the
  saved connection with `GET` requests only; Weir never changes a manager's
  settings.
