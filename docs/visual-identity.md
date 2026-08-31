# MediaMop — visual identity (web shell)

Approved **one-pager** palette (implement in `apps/web/src/styles/mediamop-tokens.css`):

| Token     | Hex       | Use                                      |
|----------|-----------|------------------------------------------|
| Charcoal | `#0B0B10` | App background                           |
| Slate    | `#1F232A` | Sidebar, cards, surfaces                 |
| Stone    | `#E7E7EA` | Primary text                             |
| Warm gold| `#D4AF37` | Brand accent, monogram, key highlights   |
| Indigo   | `#4F56EF` | Secondary accent (sparingly)             |

**Implementation:** `mediamop-tokens.css` + `mediamop-shell.css`.

## Delivery rules

- The sidebar uses a dedicated WebP mark with a 20 KiB budget; authentication and hero layouts may use the larger cropped/full variants.
- Production web builds do not emit source maps. Set `MEDIAMOP_BUILD_SOURCEMAPS=true` only for a short-lived diagnostics build and keep that output private.
- `npm run build` runs the bundle-budget check after Vite finishes. The check also caps CSS and JavaScript chunk sizes so visual polish cannot quietly turn into a slower shell.
