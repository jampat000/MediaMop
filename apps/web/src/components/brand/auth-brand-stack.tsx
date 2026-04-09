import { MediaMopLogo } from "./mediamop-logo";

/** Auth/setup — premium logo + primary blurb above the card. */
export function AuthBrandStack() {
  return (
    <div className="mm-auth-brand">
      <div className="mm-auth-brand-logo">
        <MediaMopLogo variant="auth" />
      </div>
      <p className="mm-auth-brand-tagline">Keep your media library clean, organized, and under control.</p>
    </div>
  );
}
