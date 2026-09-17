import { WeirLogo } from "./weir-logo";

/** Auth/setup — premium logo + primary blurb above the card. */
export function AuthBrandStack() {
  return (
    <div className="mm-auth-brand">
      <div className="mm-auth-brand-logo">
        <WeirLogo variant="auth" />
      </div>
      <p className="mm-auth-brand-tagline">
        Cleans every download before your media manager imports it.
      </p>
    </div>
  );
}
