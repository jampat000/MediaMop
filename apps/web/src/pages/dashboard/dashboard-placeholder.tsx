import type { ReactNode } from "react";
import { useMeQuery } from "../../lib/auth/queries";

function FrameGlyph({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect x="3.25" y="5.25" width="17.5" height="13.5" rx="1.75" stroke="currentColor" strokeWidth="1.2" />
      <path d="M3.25 8h17.5M3.25 16h17.5" stroke="currentColor" strokeWidth="0.85" opacity="0.45" />
    </svg>
  );
}

function PillarIcon({ children }: { children: ReactNode }) {
  return (
    <span className="mm-pillar__icon" aria-hidden="true">
      {children}
    </span>
  );
}

const PILLARS = [
  {
    title: "Organized",
    body: "Everything in its right place.",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
        <path d="M4 7h16v12H4V7zM4 7l2-3h12l2 3M9 11h6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    title: "Automated",
    body: "Powerful workflows that run for you.",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
        <path
          d="M12 3l1.8 5.5h5.7l-4.6 3.4 1.8 5.5L12 14.9 7.3 17.4 9 11.9 4.5 8.5h5.7L12 3z"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
  {
    title: "Trusted",
    body: "Safe, reliable, and smart.",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
        <path d="M12 21s8-4 8-10V6l-8-3-8 3v5c0 6 8 10 8 10z" strokeLinejoin="round" />
        <path d="M12 8v5l2.5 2.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    title: "Built for you",
    body: "For collectors, by a fellow collector.",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
        <path
          d="M20.8 4.6a5.5 5.5 0 00-7.8 0L12 5.6l-1-1a5.5 5.5 0 00-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 000-7.8z"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
] as const;

export function DashboardPlaceholder() {
  const me = useMeQuery();

  return (
    <div className="mm-page">
      <header className="mm-page__intro mm-page__intro--hero">
        <span className="mm-page__hero-line" aria-hidden="true" />
        <p className="mm-page__eyebrow">Overview</p>
        <h1 className="mm-page__title">Dashboard</h1>
        <p className="mm-page__subtitle">At a glance, your media workflows will live here.</p>
        <p className="mm-page__lead">
          Signed in as <strong className="font-semibold text-[var(--mm-text)]">{me.data?.username}</strong>{" "}
          <span className="text-[var(--mm-text3)]">({me.data?.role})</span>. A tidy companion for your library —
          automated, intelligent, and fastidious about quality.
        </p>
      </header>

      <p className="mm-dashboard-preamble" role="note">
        <span className="mm-dashboard-preamble__mark" aria-hidden="true" />
        Shell only: module tools are not wired yet. This layout matches the shipping product frame from the brand
        system — not a dev scaffold.
      </p>

      <div className="mm-dashboard-grid">
        <article className="mm-card mm-card--shell" data-testid="shell-ready">
          <div className="mm-card__top">
            <span className="mm-card__glyph" aria-hidden="true">
              <FrameGlyph className="text-[var(--mm-gold)]" />
            </span>
            <div className="mm-card__top-copy">
              <h2 className="mm-card__title mm-card__title--inline">Product shell</h2>
              <p className="mm-card__body mm-card__body--tight">
                Authentication, sidebar, and canvas follow the MediaMop shell spec. Fetcher-era screens are not
                recreated here — only the spine until real routes ship.
              </p>
            </div>
          </div>
        </article>
        <aside className="mm-shell-aside" aria-labelledby="mm-shell-aside-heading">
          <h2 id="mm-shell-aside-heading" className="mm-shell-aside__title">
            What is next
          </h2>
          <p className="mm-shell-aside__body">
            Library and workflow modules will appear as first-class navigation and views. Until then, Settings holds
            honest placeholders.
          </p>
        </aside>
      </div>

      <section className="mm-pillars" aria-label="Product principles">
        <h2 className="mm-pillars__heading">Why MediaMop</h2>
        <ul className="mm-pillars__grid">
          {PILLARS.map((p) => (
            <li key={p.title} className="mm-pillar">
              <PillarIcon>{p.icon}</PillarIcon>
              <h3 className="mm-pillar__title">{p.title}</h3>
              <p className="mm-pillar__body">{p.body}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
