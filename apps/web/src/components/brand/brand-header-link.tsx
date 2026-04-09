import { Link } from "react-router-dom";
import { MonogramMark } from "./monogram-mark";

type Props = { to?: string };

/** Sidebar brand — one-pager: stone “Media” + gold “Mop”, slogan below. */
export function BrandHeaderLink({ to = "/app" }: Props) {
  return (
    <Link to={to} className="mm-sidebar-brand" aria-label="MediaMop home">
      <span className="mm-sidebar-brand-row">
        <span className="mm-sidebar-mark" aria-hidden="true">
          <MonogramMark />
        </span>
        <span className="mm-sidebar-wordmark-block">
          <span className="mm-wordmark mm-wordmark--sidebar">
            <span className="mm-wordmark-media">Media</span>
            <span className="mm-wordmark-mop">Mop</span>
          </span>
        </span>
      </span>
      <p className="mm-sidebar-tagline">More order. More time. Better movies.</p>
      <p className="mm-sidebar-tagline-sub">Personal. Thoughtful. Built by and for media lovers.</p>
    </Link>
  );
}
