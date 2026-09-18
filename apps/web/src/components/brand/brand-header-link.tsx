import { Link } from "react-router-dom";
import { WeirLogo } from "./weir-logo";

type Props = { to?: string; productTitle?: string };

export function BrandHeaderLink({ to = "/", productTitle = "Weir" }: Props) {
  const label = `${productTitle} home`;
  return (
    <Link to={to} className="mm-sidebar-brand" aria-label={label}>
      <div className="mm-sidebar-brand-logo">
        <WeirLogo variant="sidebar" />
      </div>
      {/* Both of the things Weir does, and neither overstated. The old line — "Cleans every
          download before your media manager imports it." — described only the way in, and by
          the time library mode shipped (#568, #575) the blurb under the wordmark was denying
          half the product: Processing also cleans files already sitting in a library, in place.
          "every" was an overclaim besides; a library's rules skip files all the time, which is
          the whole reason the Files tab says why each one was or was not processed. */}
      <p className="mm-sidebar-tagline">
        Cleans new downloads, and files already in your library.
      </p>
    </Link>
  );
}
