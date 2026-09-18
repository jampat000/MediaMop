type WeirLogoVariant = "sidebar" | "auth";

type Props = {
  variant?: WeirLogoVariant;
  className?: string;
};

/**
 * The Weir mark (#581): water turning over a weir crest into the tailrace, with the apron
 * below it. It replaces the hand-drawn "low wall with water over it" placeholder from #564.
 *
 * The geometry is generated, not hand-drawn. `design-options/logos-round4/build/trace.py`
 * thresholds the accepted source render to two colours and fits circles to every band edge;
 * `mark.py` regularises those measurements onto a 24-unit grid and emits these exact three paths
 * into `packaging/brand/weir-mark.svg`, which is in turn the source for the favicon, tray icon
 * and docs logo (`scripts/generate-brand-icons.py`). Drawn inline here rather than as an <img>
 * so it follows the theme tokens.
 *
 * This is the three-stream mark — the one traced directly off the Midjourney render James
 * accepted, and the one he asked for by name after #582 shipped a two-stream simplification
 * instead ("logo is not exact I want this one"). Three streams do not survive a 16px favicon:
 * the bands are sub-pixel at that size and fuse into a smear (see mark.py's SHIPPED_STREAMS
 * comment and design-options/logos-round4/gate-16px.png). But the sidebar mark here is never
 * rendered anywhere near that small, so it carries no such penalty, and the extra stream is what
 * makes it read as three-dimensional water rather than a flat arch. The 16px .ico frame is the
 * only place that trade-off still applies — see scripts/generate-brand-icons.py and
 * packaging/brand/README.md for the optical-size split.
 *
 * Three paths, all one colour. The mark used to be two tones — gold water over a stone wall —
 * but the Windows tray icon is a single-colour mask and cannot carry a second tone, so a
 * two-tone mark meant the tray never matched the app. If you change the geometry, change it in
 * mark.py and re-run `python design-options/logos-round4/build/build.py`, which rewrites the
 * brand SVGs and prints the path data to paste here. Do not edit the `d` attributes by hand.
 */
function WeirMark({ className }: { className?: string }) {
  return (
    <svg
      className={["mm-logo-mark", className].filter(Boolean).join(" ")}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      {/* The outer stream: the vertical approach, the turn over the crest, and the flat cut
          where it tips into the tailrace. This one carries the whole silhouette. */}
      <path
        className="mm-logo-mark__stream"
        d="M3.65 16.55L3.65 13.7A9.65 9.65 0 0 1 21.889 9.3L19.74 9.3A7.8 7.8 0 0 0 5.5 13.7L5.5 16.55Z"
      />
      {/* The middle stream: a repeat of the outer one on a smaller radius, carrying no
          structure of its own. This is the band #582 dropped for 16px legibility; it is back
          here, and everywhere above 16px, because nothing else is rendered that small. */}
      <path
        className="mm-logo-mark__stream"
        d="M7.05 16.55L7.05 13.7A6.25 6.25 0 0 1 17.739 9.3L13.3 9.3A4.4 4.4 0 0 0 8.9 13.7L8.9 16.55Z"
      />
      {/* The inner stream, its quarter turn into the tailrace bar, and the apron running back
          out to the left: one outline, because a shared edge between two shapes shows up as a
          hairline seam at fractional raster sizes. */}
      <path
        className="mm-logo-mark__stream"
        d="M10.45 13.7L10.45 18.1L2.1 18.1L2.1 19.95L12.3 19.95L12.3 13.7A1 1 0 0 1 13.3 12.7L21.889 12.7L21.889 10.85L13.3 10.85A2.85 2.85 0 0 0 10.45 13.7Z"
      />
    </svg>
  );
}

/** Mark plus the "Weir" wordmark set in the app font. */
export function WeirLogo({ variant = "auth", className }: Props) {
  return (
    <span
      className={["mm-logo", `mm-logo--${variant}`, className]
        .filter(Boolean)
        .join(" ")}
      role="img"
      aria-label="Weir"
    >
      <WeirMark />
      <span className="mm-logo-wordmark" aria-hidden="true">
        Weir
      </span>
    </span>
  );
}
