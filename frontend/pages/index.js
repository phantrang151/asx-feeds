import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import styles from '../styles/Landing.module.css';

const SCREENSHOTS = [
  {
    src: '/screenshots/fig-1-define.png',
    alt: "Dashboard showing the 'Add a ticker' and 'Create a feed' forms next to a list of configured feeds for TLS.AX and ANZ.AX, including Network Stability, Revenue Trend, Red Flags, and Business Strategy",
    caption: 'Define exactly what you want tracked',
  },
  {
    src: '/screenshots/fig-2-alerts.png',
    alt: "Alerts page for TLS.AX showing a synthesized cross-feed insight above dated, sourced news items classified under feeds like Business Strategy and Revenue Trend",
    caption: 'One insight, built across every feed',
  },
  {
    src: '/screenshots/fig-3-ask.png',
    alt: "Ask a question page showing an AI-generated, cited answer to 'Why is Telstra's profit increasing?' with a list of source references",
    caption: 'Ask anything, get a cited answer',
  },
];

function ExpandIcon() {
  return (
    <svg className={styles.expandIcon} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M9 3H3v6M15 3h6v6M21 15v6h-6M3 15v6h6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Lightbox({ shot, onClose }) {
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = '';
    };
  }, [onClose]);

  return (
    <div className={styles.lightboxOverlay} onClick={onClose} role="dialog" aria-modal="true" aria-label={shot.alt}>
      <button type="button" className={styles.lightboxClose} onClick={onClose} aria-label="Close">
        ×
      </button>
      <img
        className={styles.lightboxImg}
        src={shot.src}
        alt={shot.alt}
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}

const TICKERS = [
  { sym: 'BHP.AX', delta: '+1.2%', dir: 'up' },
  { sym: 'CBA.AX', delta: '-0.4%', dir: 'down' },
  { sym: 'CSL.AX', delta: '+0.8%', dir: 'up' },
  { sym: 'TLS.AX', delta: '+0.3%', dir: 'up' },
  { sym: 'WES.AX', delta: '-0.6%', dir: 'down' },
  { sym: 'RIO.AX', delta: '+1.9%', dir: 'up' },
  { sym: 'WOW.AX', delta: '-0.2%', dir: 'down' },
  { sym: 'NAB.AX', delta: '+0.5%', dir: 'up' },
];

function TickerTape() {
  // Rendered twice back to back so the marquee's -50% translateX loop is seamless.
  const items = [...TICKERS, ...TICKERS];
  return (
    <div className={styles.tickerTape}>
      <div className={styles.wrap}>
        <span className={styles.exchangeBadge}>ASX</span>
        <div className={styles.tapeTrack} aria-hidden="true">
          <ul>
            {items.map((t, i) => (
              <li key={i}>
                <span className={styles.sym}>{t.sym}</span>{' '}
                <span className={styles[t.dir]}>{t.delta}</span>
              </li>
            ))}
          </ul>
        </div>
        <span className={styles.finePrint}>Illustrative tickers, not live data</span>
      </div>
    </div>
  );
}

export default function Home() {
  const { user } = useAuth();
  const [lightboxIndex, setLightboxIndex] = useState(null);

  return (
    <div className={styles.landing}>
      <Head>
        <title>TickerThesis — Define a thesis. Let the news test it.</title>
      </Head>

      <div className={styles.topbar}>
        <div className={styles.wrap}>
          <div className={styles.wordmark}>
            TICKER<span className={styles.dot}>·</span>THESIS
          </div>
          <nav>
            <Link href="/technical">Technical overview</Link>
            {user ? <Link href="/dashboard">Dashboard</Link> : <Link href="/signin">Sign in</Link>}
          </nav>
        </div>
      </div>

      <TickerTape />

      <section className={styles.hero}>
        <div className={styles.wrap}>
          <h1>
            Define a thesis.
            <br />
            <span className={styles.accentLine}>Let the news test it.</span>
          </h1>
          <p className={styles.subhead}>
            Googling a company gives you every article about it, in no particular order. TickerThesis
            sorts that news into the categories you define, then synthesizes what it finds into one
            connected insight. One place to see what&apos;s actually going on, not a stack of articles
            to read yourself.
          </p>
          <div className={styles.ctas}>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnPrimary}`}
              onClick={() => document.getElementById('screenshots')?.scrollIntoView({ behavior: 'smooth' })}
            >
              See it in action ↓
            </button>
            {user ? (
              <Link href="/dashboard" className={styles.secondaryLink}>
                Go to dashboard
              </Link>
            ) : (
              <Link href="/signup" className={styles.secondaryLink}>
                Sign up free, no credit card
              </Link>
            )}
          </div>
        </div>
      </section>

      <section>
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>HOW IT WORKS</div>
          <div className={styles.valueGrid}>
            <div className={styles.valueCard}>
              <span className={styles.tag}>[Define]</span>
              <h3>Your thesis, not a generic feed</h3>
              <p>
                Define exactly what you want tracked per company — a preset thesis like Revenue Trend, or
                something fully custom, like &quot;is customer growth being offset by churn.&quot; News gets
                sorted into the right thesis automatically. No scrolling through everything to find what&apos;s
                relevant to you.
              </p>
            </div>
            <div className={styles.valueCard}>
              <span className={styles.tag}>[Track]</span>
              <h3>One connected insight, not a pile of articles</h3>
              <p>
                Every time new evidence lands, TickerThesis synthesizes what your feeds add up to together —
                is growth coming from revenue or from cost-cutting, is a scandal outweighing the upside —
                refreshed automatically, not something you have to piece together yourself.
              </p>
            </div>
            <div className={styles.valueCard}>
              <span className={styles.tag}>[Ask]</span>
              <h3>Ask, get a sourced answer</h3>
              <p>
                Ask a plain-language question and get an answer built only from retrieved evidence, with a
                citation for every claim. Not a confident-sounding guess.
              </p>
            </div>
            <div className={styles.valueCard}>
              <span className={styles.tag}>[Verify]</span>
              <h3>Transparent by design</h3>
              <p>
                No financial advice, no black-box claims. Every piece of evidence links straight to its source
                article — you can verify everything yourself.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section id="screenshots">
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>THE PRODUCT, IN THREE SCREENS</div>
          <div className={styles.shotStrip}>
            {SCREENSHOTS.map((shot, i) => (
              <div key={shot.src}>
                <button
                  type="button"
                  className={styles.shot}
                  onClick={() => setLightboxIndex(i)}
                  aria-label={`View full size: ${shot.caption}`}
                >
                  <img src={shot.src} alt={shot.alt} loading="lazy" />
                  <ExpandIcon />
                </button>
                <p className={styles.shotCap}>{shot.caption}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {lightboxIndex !== null && (
        <Lightbox shot={SCREENSHOTS[lightboxIndex]} onClose={() => setLightboxIndex(null)} />
      )}

      <div className={styles.disclaimer}>
        <div className={styles.wrap}>
          <p>
            TickerThesis is an AI-generated research aid, not financial advice. All content should be
            independently verified. This is a portfolio/demo project — see the technical page for details on
            data sources and design.
          </p>
        </div>
      </div>

      <footer className={styles.siteFooter}>
        <div className={styles.wrap}>
          <span className={styles.copy}>© TickerThesis — portfolio project</span>
          <nav>
            <Link href="/technical">About (technical)</Link>
            <Link href="/signup">Sign up</Link>
            <span>GitHub</span>
          </nav>
        </div>
      </footer>
    </div>
  );
}
