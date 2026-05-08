import logoSrc from "./mediamop-logo-premium.png";
import logoCroppedSrc from "./mediamop-logo-premium-cropped.png";

export type MediaMopLogoVariant = "sidebar" | "auth" | "hero";

type Props = {
  variant?: MediaMopLogoVariant;
  className?: string;
};

const variantClass: Record<MediaMopLogoVariant, string> = {
  sidebar: "mm-logo mm-logo--sidebar",
  auth: "mm-logo mm-logo--auth",
  hero: "mm-logo mm-logo--hero",
};

/** Premium raster logo — single source of truth; preserves aspect ratio (object-fit: contain). */
export function MediaMopLogo({ variant = "auth", className }: Props) {
  const src = variant === "hero" ? logoSrc : logoCroppedSrc;
  return (
    <img
      src={src}
      alt="MediaMop"
      className={[variantClass[variant], className].filter(Boolean).join(" ")}
      decoding="async"
    />
  );
}
