import { Link } from "react-router-dom";
import { MonogramMark } from "./monogram-mark";

type Props = { to?: string };

/** Sidebar brand — one-pager: stone “Media” + gold “Mop”, slogan below. */
export function BrandHeaderLink({ to = "/app" }: Props) {
  return (
    <Link to={to} className="mb-sidebar-brand" aria-label="MediaMop home">
      <span className="mb-sidebar-brand-row">
        <span className="mb-sidebar-mark" aria-hidden="true">
          <MonogramMark />
        </span>
        <span className="mb-sidebar-wordmark-block">
          <span className="mb-wordmark mb-wordmark--sidebar">
            <span className="mb-wordmark-media">Media</span>
            <span className="mb-wordmark-mop">Mop</span>
          </span>
        </span>
      </span>
      <p className="mb-sidebar-tagline">More order. More time. Better movies.</p>
      <p className="mb-sidebar-tagline-sub">Personal. Thoughtful. Built by and for media lovers.</p>
    </Link>
  );
}
