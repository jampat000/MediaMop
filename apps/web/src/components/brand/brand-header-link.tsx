import { Link } from "react-router-dom";
import { MediaMopLogo } from "./mediamop-logo";

type Props = { to?: string };

export function BrandHeaderLink({ to = "/app" }: Props) {
  return (
    <Link to={to} className="mm-sidebar-brand" aria-label="MediaMop home">
      <div className="mm-sidebar-brand-logo">
        <MediaMopLogo variant="sidebar" />
      </div>
      <p className="mm-sidebar-tagline">One app to clean up your entire media workflow.</p>
      <p className="mm-sidebar-tagline-sub">Personal. Thoughtful. Built by and for media lovers.</p>
    </Link>
  );
}
