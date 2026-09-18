import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';

import styles from './index.module.css';

const features = [
  {
    title: 'Processing',
    description:
      'Cleans new downloads, and files already in your library: keep the audio and subtitle tracks you want and remove the rest, library by library, with configurable worker lanes.',
    screenshot: '/Weir/img/processing.png',
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
            to="https://github.com/jampat000/Weir">
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

function InHandPreview(): ReactNode {
  return (
    <section className={styles.preview}>
      <div className="container">
        <h2>In hand, at a glance</h2>
        <p>
          Files Weir is responsible for right now, between your media manager
          handing them over and getting them back.
        </p>
        <img
          src="/Weir/img/in-hand.png"
          alt="Weir In hand page"
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
        <InHandPreview />
      </main>
    </Layout>
  );
}
