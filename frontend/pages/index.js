import Head from 'next/head';
import Link from 'next/link';
import { useAuth } from '../context/AuthContext';
import styles from '../styles/Landing.module.css';

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
            sorts that same news into the categories you define — Revenue Trend, Network Quality,
            Customer Churn, anything else — automatically.
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
            <div>
              <div className={styles.shot}>
                <span className={`${styles.exhibit} ${styles.tag}`}>[Fig. 1]</span>
                <svg viewBox="0 0 48 48" fill="none" role="img" aria-label="Crosshair icon representing defining a thesis">
                  <circle cx="24" cy="24" r="15" stroke="currentColor" strokeWidth="1.6" />
                  <circle cx="24" cy="24" r="3" fill="currentColor" />
                  <line x1="24" y1="2" x2="24" y2="11" stroke="currentColor" strokeWidth="1.6" />
                  <line x1="24" y1="37" x2="24" y2="46" stroke="currentColor" strokeWidth="1.6" />
                  <line x1="2" y1="24" x2="11" y2="24" stroke="currentColor" strokeWidth="1.6" />
                  <line x1="37" y1="24" x2="46" y2="24" stroke="currentColor" strokeWidth="1.6" />
                </svg>
              </div>
              <p className={styles.shotCap}>Define exactly what you want tracked</p>
            </div>
            <div>
              <div className={styles.shot}>
                <span className={`${styles.exhibit} ${styles.tag}`}>[Fig. 2]</span>
                <svg viewBox="0 0 48 48" fill="none" role="img" aria-label="Stacked cards icon representing classified daily evidence">
                  <rect x="10" y="6" width="28" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
                  <rect x="10" y="19" width="28" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
                  <rect x="10" y="32" width="28" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
                </svg>
              </div>
              <p className={styles.shotCap}>Daily evidence, classified and sourced</p>
            </div>
            <div>
              <div className={styles.shot}>
                <span className={`${styles.exhibit} ${styles.tag}`}>[Fig. 3]</span>
                <svg viewBox="0 0 48 48" fill="none" role="img" aria-label="Speech bubble with citation mark representing sourced answers">
                  <path d="M6 10h36v22H20l-8 8v-8H6z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
                  <text x="24" y="26" textAnchor="middle" fontSize="12" fill="currentColor" fontFamily="var(--mono)">[1]</text>
                </svg>
              </div>
              <p className={styles.shotCap}>Ask anything, get a cited answer</p>
            </div>
          </div>
        </div>
      </section>

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
