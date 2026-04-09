import { MediaMopLogo } from "./mediamop-logo";

/** Auth/setup — premium logo + taglines above the card. */
export function AuthBrandStack() {
  return (
    <div className="mm-auth-brand">
      <div className="mm-auth-brand-logo">
        <MediaMopLogo variant="auth" />
      </div>
      <p className="mm-auth-brand-tagline">One app to clean up your entire media workflow.</p>
      <p className="mm-auth-brand-tagline-sub">Personal. Thoughtful. Built by and for media lovers.</p>
    </div>
  );
}
