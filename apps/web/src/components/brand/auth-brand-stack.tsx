import { MonogramMark } from "./monogram-mark";

/** Auth/setup — same wordmark system as sidebar (one-pager). */
export function AuthBrandStack() {
  return (
    <div className="mm-auth-brand">
      <span className="mm-sidebar-mark mm-sidebar-mark--auth" aria-hidden="true">
        <MonogramMark />
      </span>
      <div className="mm-wordmark mm-wordmark--auth">
        <span className="mm-wordmark-media">Media</span>
        <span className="mm-wordmark-mop">Mop</span>
      </div>
      <p className="mm-auth-brand-tagline">More order. More time. Better movies.</p>
      <p className="mm-auth-brand-tagline-sub">Personal. Thoughtful. Built by and for media lovers.</p>
    </div>
  );
}
