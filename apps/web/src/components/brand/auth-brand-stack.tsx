import { MonogramMark } from "./monogram-mark";

/** Auth/setup — same wordmark system as sidebar (one-pager). */
export function AuthBrandStack() {
  return (
    <div className="mb-auth-brand">
      <span className="mb-sidebar-mark mb-sidebar-mark--auth" aria-hidden="true">
        <MonogramMark />
      </span>
      <div className="mb-wordmark mb-wordmark--auth">
        <span className="mb-wordmark-media">Media</span>
        <span className="mb-wordmark-mop">Mop</span>
      </div>
      <p className="mb-auth-brand-tagline">More order. More time. Better movies.</p>
      <p className="mb-auth-brand-tagline-sub">Personal. Thoughtful. Built by and for media lovers.</p>
    </div>
  );
}
