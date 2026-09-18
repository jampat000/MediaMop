import { WeirLogo } from "./weir-logo";

/** Auth/setup — premium logo + primary blurb above the card. */
export function AuthBrandStack() {
  return (
    <div className="mm-auth-brand">
      <div className="mm-auth-brand-logo">
        <WeirLogo variant="auth" />
      </div>
      {/* The same sentence the sidebar carries (brand-header-link.tsx), kept identical on
          purpose: these are the two places Weir describes itself, and they should not say two
          different things. The reason it changed is written up there. */}
      <p className="mm-auth-brand-tagline">
        Cleans new downloads, and files already in your library.
      </p>
    </div>
  );
}
