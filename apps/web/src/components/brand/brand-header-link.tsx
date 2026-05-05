import { Link } from "react-router-dom";
import { MediaMopLogo } from "./mediamop-logo";

type Props = { to?: string; productTitle?: string };

export function BrandHeaderLink({
  to = "/",
  productTitle = "MediaMop",
}: Props) {
  const label = `${productTitle} home`;
  return (
    <Link to={to} className="mm-sidebar-brand" aria-label={label}>
      <div className="mm-sidebar-brand-logo">
        <MediaMopLogo variant="sidebar" />
      </div>
      <p className="mm-sidebar-product-title">{productTitle}</p>
      <p className="mm-sidebar-tagline">
        Keep your library clean and under control.
      </p>
    </Link>
  );
}
