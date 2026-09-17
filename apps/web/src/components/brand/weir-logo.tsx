import logoSrc from "./weir-logo-premium.webp";
import logoCroppedSrc from "./weir-logo-premium-cropped.webp";
import logoSidebarSrc from "./weir-logo-sidebar.webp";

export type WeirLogoVariant = "sidebar" | "auth" | "hero";

type Props = {
  variant?: WeirLogoVariant;
  className?: string;
};

const variantClass: Record<WeirLogoVariant, string> = {
  sidebar: "mm-logo mm-logo--sidebar",
  auth: "mm-logo mm-logo--auth",
  hero: "mm-logo mm-logo--hero",
};

/** Premium raster logo — single source of truth; preserves aspect ratio (object-fit: contain). */
export function WeirLogo({ variant = "auth", className }: Props) {
  const src =
    variant === "hero"
      ? logoSrc
      : variant === "sidebar"
        ? logoSidebarSrc
        : logoCroppedSrc;
  return (
    <img
      src={src}
      alt="Weir"
      className={[variantClass[variant], className].filter(Boolean).join(" ")}
      decoding="async"
    />
  );
}
