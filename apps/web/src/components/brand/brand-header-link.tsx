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
      <p className="mm-sidebar-tagline">
        Cleans every download before your media manager imports it.
      </p>
    </Link>
  );
}
