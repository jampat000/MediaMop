# Refiner and media-manager coverage

Refiner's basic watched-folder remux is standalone. After a file has passed the
local age, settling, access, schedule, and lifecycle checks, it can be processed
without Radarr, Sonarr, Deluno, or another manager.

| Workflow | Standalone | Radarr/Sonarr | Deluno | Native hand-off |
| --- | --- | --- | --- | --- |
| Watched-folder remux | Supported; local safety gates apply | Supported | Supported | Supported |
| Upstream import protection | Reduced safety: no upstream import check | Enhanced when the connection answers | Enhanced when the connection answers | Depends on the hand-off signal |
| Library discovery/sync | Manual libraries | Optional convenience | Optional convenience | Optional convenience |
| Destructive cleanup requiring manager truth | Safely held until MediaMop can confirm | Available when the manager answers | Available when the manager answers | Depends on the hand-off contract |
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
