import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';

import styles from './index.module.css';

const features = [
  {
    title: 'Refiner',
    description:
      'Remux media files into cleaner, more consistent outputs with configurable worker lanes.',
    screenshot: '/MediaMop/img/refiner.png',
  },
  {
    title: 'Pruner',
    description:
      'Find and safely remove media matching your cleanup rules with preview before deletion.',
    screenshot: '/MediaMop/img/pruner.png',
  },
  {
    title: 'Subber',
    description:
      'Sync libraries from Sonarr and Radarr, track subtitle state, and manage providers.',
    screenshot: '/MediaMop/img/subber.png',
  },
];

function Hero(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <header className={clsx('hero', styles.hero)}>
      <div className="container">
        <h1 className="hero__title">{siteConfig.title}</h1>
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <div className={styles.buttons}>
          <Link className="button button--primary button--lg" to="/docs/quickstart">
            Get Started
          </Link>
          <Link
            className="button button--secondary button--lg"
            to="https://github.com/jampat000/MediaMop">
            GitHub
          </Link>
        </div>
      </div>
    </header>
  );
}

function Feature({
  title,
  description,
  screenshot,
}: {
  title: string;
  description: string;
  screenshot: string;
}): ReactNode {
  return (
    <div className={clsx('col col--4')}>
      <div className={styles.featureCard}>
        <img
          src={screenshot}
          alt={`${title} screenshot`}
          className={styles.featureImage}
        />
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
    </div>
  );
}

function Features(): ReactNode {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {features.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}

function DashboardPreview(): ReactNode {
  return (
    <section className={styles.preview}>
      <div className="container">
        <h2>Dashboard at a glance</h2>
        <p>
          Live system health, recent work, logs, and core app configuration in
          one place.
        </p>
        <img
          src="/MediaMop/img/dashboard.png"
          alt="MediaMop Dashboard"
          className={styles.dashboardImage}
        />
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout title="Home" description={siteConfig.tagline}>
      <Hero />
      <main>
        <Features />
        <DashboardPreview />
      </main>
    </Layout>
  );
}
