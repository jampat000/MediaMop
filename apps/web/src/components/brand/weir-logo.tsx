type WeirLogoVariant = "sidebar" | "auth";

type Props = {
  variant?: WeirLogoVariant;
  className?: string;
};

/**
 * The Weir mark: a low wall with water spilling over its crest. Drawn inline so it follows the
 * theme tokens (`--mm-brand-*`). The same geometry lives in `packaging/brand/weir-mark.svg`, the
 * source for the favicon, tray icon and docs logo (`scripts/generate-brand-icons.py`).
 */
function WeirMark({ className }: { className?: string }) {
  return (
    <svg
      className={["mm-logo-mark", className].filter(Boolean).join(" ")}
      viewBox="0 0 32 32"
      aria-hidden="true"
      focusable="false"
    >
      <g transform="translate(0 -3)">
        <path
          className="mm-logo-mark__wall"
          d="M5 19H13C16.3 19 17.4 20.7 18 23.4L18.6 26.2C18.8 27.1 18.2 28 17.2 28H5C3.9 28 3 27.1 3 26V21C3 19.9 3.9 19 5 19Z"
        />
        <path
          className="mm-logo-mark__water"
          d="M3 13.2C5.4 11.2 7.8 11.2 10.2 13.2C12 14.7 13.4 14.4 15 14C19.6 13 21.3 15.6 22.2 19.6C23 23.2 24.4 25.6 29 25.6"
        />
      </g>
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
