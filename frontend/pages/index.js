import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import styles from '../styles/Landing.module.css';

// One step per product screen. On desktop the active step's screen is shown beside the list;
// on narrow screens every step is stacked with its own screen.
const STEPS = [
  {
    src: '/screenshots/fig-1-feeds.png',
    alt: "Dashboard with the 'Add a ticker' and 'Create a feed' forms beside NAB.AX's feeds: a custom Workforce & Cost Cutting feed with its match threshold, Edit and Refresh controls, and common Revenue Trend and Business Strategy feeds, each with its description",
    window: 'Dashboard',
    step: '01',
    title: 'Define & track',
    text: 'Add the ASX tickers you follow and create a feed for each question you care about: a preset like Revenue Trend, or your own, like "is customer growth being offset by churn?"',
  },
  {
    src: '/screenshots/fig-2-insight.png',
    alt: "Alerts page for NAB.AX: a cross-feed insight linking NAB's 2,500 job cuts, AI investment and revenue trend, with evidence counts per feed and Business Strategy flagged as not enough evidence, above the dated, sourced articles sorted into each feed",
    window: 'Alerts · NAB.AX',
    step: '02',
    title: 'One insight, across every feed',
    text: 'New articles are sorted into your feeds and joined into one insight: is growth coming from revenue or from cost-cutting? Every piece links to its source, and when the evidence is too thin to conclude anything, it says so.',
    note: 'Informational only, never buy or sell advice.',
  },
  {
    src: '/screenshots/fig-3-answer.png',
    alt: "Answer to 'What has changed in my NAB investment thesis based on the latest news?', listing the user's own feed snapshots and news articles as references before explaining the new workforce restructuring, interest rate and analyst sentiment developments",
    window: 'Ask a question',
    step: '03',
    title: 'Ask & verify',
    text: "Ask any question in plain language and get an answer built on your research, not a generic search. TickerThesis starts from the feeds you created and the insights they've built up over time, then draws on the news and company reports behind them. Every reference is listed, so you can check each claim.",
    points: [
      'Grounded in your own feeds and tickers',
      "Builds on past insights, not just today's news",
      'Every reference listed with the answer',
    ],
    note: 'Informational only, never buy or sell advice.',
  },
];

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Front-page numbers from GET /api/public/site-stats - a weekly snapshot (stats/site_stats.py),
// so the label says "updated weekly" rather than "live". feeds_created is deliberately not
// shown: a count of feeds says little about what the product does for anyone.
const HERO_STATS = [
  { key: 'articles_matched', label: 'articles matched', one: 'article matched' },
  { key: 'insights_generated', label: 'insights generated', one: 'insight generated' },
  { key: 'active_researchers', label: 'active researchers', one: 'active researcher' },
];

// Hidden entirely when the snapshot can't be loaded (404 before the first weekly run, or the
// API is down) - placeholders that never fill in would look broken.
function HeroStats() {
  const [stats, setStats] = useState(undefined); // undefined = loading, null = unavailable
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/api/public/site-stats`)
      .then((res) => (res.ok ? res.json() : null))
      .catch(() => null)
      .then((data) => {
        if (!cancelled) setStats(data);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (stats === null) return null;
  return (
    <div className={styles.heroStats}>
      <div className={styles.heroStatsLabel}>
        <span className={styles.statusDot} aria-hidden="true" />
        From the platform · Updated weekly
      </div>
      <dl className={styles.heroStatsGrid}>
        {HERO_STATS.map(({ key, label, one }) => (
          <div key={key}>
            <dt>{stats && Number(stats[key]) === 1 ? one : label}</dt>
            <dd>
              {stats ? Number(stats[key]).toLocaleString('en-AU') : <span className={styles.statPlaceholder} aria-label="Loading" />}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// How long each step stays active while the steps auto-advance; matches the progress bar animation.
const STEP_DURATION_MS = 7000;

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

// A screenshot framed as an app window, clickable to open full size.
function ShotFrame({ shot, onOpen }) {
  return (
    <button
      type="button"
      className={styles.shotFrame}
      onClick={onOpen}
      aria-label={`View full size: ${shot.title}`}
    >
      <span className={styles.windowBar} aria-hidden="true">
        <span className={styles.windowDots}>
          <i />
          <i />
          <i />
        </span>
        <span className={styles.windowTitle}>{shot.window}</span>
      </span>
      <span className={styles.shotViewport}>
        <img src={shot.src} alt={shot.alt} loading="lazy" />
        <ExpandIcon />
      </span>
    </button>
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

// Step list beside a single screen. Steps auto-advance (driven by the progress bar's
// animationend, so reduced-motion users get no auto-advance) until the visitor picks one.
function ProductSteps({ onOpen }) {
  const [active, setActive] = useState(0);
  const [autoplay, setAutoplay] = useState(true);

  const select = (i) => {
    setActive(i);
    setAutoplay(false);
  };

  const onKeyDown = (e) => {
    const delta = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
    if (!delta) return;
    e.preventDefault();
    const next = (active + delta + STEPS.length) % STEPS.length;
    select(next);
    document.getElementById(`product-step-${next}`)?.focus();
  };

  return (
    <div className={styles.productSteps}>
      <div className={styles.stepList} role="tablist" aria-orientation="vertical" onKeyDown={onKeyDown}>
        {STEPS.map((shot, i) => (
          <div key={shot.src} className={`${styles.stepItem} ${i === active ? styles.stepItemActive : ''}`}>
            <button
              type="button"
              id={`product-step-${i}`}
              role="tab"
              aria-selected={i === active}
              aria-controls="product-step-panel"
              tabIndex={i === active ? 0 : -1}
              className={`${styles.stepButton} ${i === active ? styles.stepButtonActive : ''}`}
              onClick={() => select(i)}
            >
              <span className={styles.stepNum}>{shot.step}</span>
              <span className={styles.stepBody}>
                <span className={styles.stepTitle}>{shot.title}</span>
                <span className={styles.stepText}>{shot.text}</span>
                {/* spans, not <ul>: a <button> may only contain phrasing content */}
                {shot.points && (
                  <span className={styles.stepPoints}>
                    {shot.points.map((point) => (
                      <span key={point}>{point}</span>
                    ))}
                  </span>
                )}
                {shot.note && <span className={styles.stepNote}>{shot.note}</span>}
              </span>
              {autoplay && i === active && (
                <span
                  key={active}
                  className={styles.stepProgress}
                  style={{ animationDuration: `${STEP_DURATION_MS}ms` }}
                  onAnimationEnd={() => setActive((active + 1) % STEPS.length)}
                  aria-hidden="true"
                />
              )}
            </button>
            {/* Narrow screens: each step carries its own screen; hidden on desktop. */}
            <div className={styles.stepShotInline}>
              <ShotFrame shot={shot} onOpen={() => onOpen(i)} />
            </div>
          </div>
        ))}
      </div>
      <div
        id="product-step-panel"
        role="tabpanel"
        aria-labelledby={`product-step-${active}`}
        className={styles.stepShot}
      >
        {/* key: remount on every step change so the capture fades in (see .stepShot img) */}
        <ShotFrame key={active} shot={STEPS[active]} onOpen={() => onOpen(active)} />
      </div>
    </div>
  );
}

// Decorative only: no prices, just symbols cycling through the three tape colours.
const TICKERS = [
  { sym: 'BHP.AX', tone: 'up' },
  { sym: 'CBA.AX', tone: 'sym' },
  { sym: 'CSL.AX', tone: 'down' },
  { sym: 'TLS.AX', tone: 'up' },
  { sym: 'WES.AX', tone: 'sym' },
  { sym: 'RIO.AX', tone: 'down' },
  { sym: 'WOW.AX', tone: 'up' },
  { sym: 'NAB.AX', tone: 'sym' },
  { sym: 'ANZ.AX', tone: 'down' },
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
              <li key={i} className={`${styles.sym} ${styles[t.tone]}`}>
                {t.sym}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

// Stroke icons for the hero diagram, drawn on a 24px grid.
const ICON_PATHS = {
  news: 'M5 4h11v16H5zM16 8h3v10a2 2 0 0 1-2 2M8 8h5M8 12h5M8 16h3',
  reports: 'M5 20V10M10 20V4M15 20v-7M20 20H3',
  history: 'M3 12a9 9 0 1 0 3-6.7M3 4v4h4M12 8v4l3 2',
  loop: 'M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4',
  synth: 'M6 6a2 2 0 1 0 0 .01M6 18a2 2 0 1 0 0 .01M18 12a2 2 0 1 0 0 .01M8 7l8 4M8 17l8-4',
  check: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12l3 3 5-6',
};

function Icon({ name, className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d={ICON_PATHS[name]} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// "Pulled weekly": the pipeline runs on .github/workflows/weekly-pipeline.yml's Sunday schedule.
// Past insights are the user's earlier ticker_insights snapshots (what get_my_thesis_tool reads).
const HERO_SOURCES = [
  { icon: 'news', label: 'Financial news', sub: 'Pulled weekly' },
  { icon: 'reports', label: 'Company reports', sub: 'Results & filings' },
  { icon: 'history', label: 'Past insights', sub: 'Yours, from earlier runs', own: true },
];

const HERO_FEEDS = ['Revenue Trend', 'Red Flags', 'Business Strategy'];

function HeroDiagram() {
  return (
    <div
      className={styles.heroCard}
      role="img"
      aria-label="Financial news, company reports and your past insights flow into TickerThesis AI, sorted into your feeds such as Revenue Trend, Red Flags, Business Strategy or your own, producing your investment insight, which becomes a past insight for the next run."
    >
      <div className={styles.sourceGrid}>
        {HERO_SOURCES.map((s) => (
          <div key={s.label} className={`${styles.sourceTile} ${s.own ? styles.sourceTileOwn : ''}`}>
            <span className={styles.sourceIcon}>
              <Icon name={s.icon} />
            </span>
            <span className={styles.sourceLabel}>{s.label}</span>
            <span className={styles.sourceSub}>{s.sub}</span>
          </div>
        ))}
      </div>
      <svg className={styles.funnel} viewBox="0 0 600 48" preserveAspectRatio="none" aria-hidden="true">
        <path
          d="M100 0 C100 30, 300 18, 300 48 M300 0 L300 48 M500 0 C500 30, 300 18, 300 48"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div className={styles.aiPanel}>
        <div className={styles.aiBar}>
          <span className={styles.aiName}>
            <Icon name="synth" className={styles.aiIcon} />
            TickerThesis AI
          </span>
        </div>
        <div className={styles.aiFeeds}>
          <div className={styles.aiFeedsLabel}>Sorted into your feeds</div>
          <div className={styles.feedChips}>
            {HERO_FEEDS.map((f) => (
              <span key={f} className={styles.feedChip}>{f}</span>
            ))}
            <span className={`${styles.feedChip} ${styles.feedChipOwn}`}>+ Your own</span>
          </div>
        </div>
      </div>
      <div className={styles.flowArrow} aria-hidden="true">↓</div>
      <div className={styles.insightBox}>
        <Icon name="check" className={styles.insightIcon} />
        <span className={styles.insightTitle}>Your investment insight</span>
        <span className={styles.insightLoop}>
          <Icon name="loop" />
          Becomes a past insight
        </span>
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
        <div className={`${styles.wrap} ${styles.heroGrid}`}>
          <div className={styles.heroText}>
            <h1>
              <span className={styles.leadLine}>Define a thesis.</span>
              <br />
              <span className={styles.softLine}>Let the news test it.</span>
              <br />
              <span className={styles.accentLine}>Turn news into investment insight.</span>
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
                <Link href="/dashboard" className={`${styles.btn} ${styles.btnGhost}`}>
                  Go to dashboard
                </Link>
              ) : (
                <Link href="/signup" className={`${styles.btn} ${styles.btnGhost}`}>
                  Sign up free
                </Link>
              )}
            </div>
            <HeroStats />
          </div>
          <HeroDiagram />
        </div>
      </section>

      <section id="screenshots">
        <div className={styles.wrap}>
          <div className={styles.eyebrow}>THE PRODUCT</div>
          <h2 className={styles.sectionTitle}>From your thesis to evidence-backed insight</h2>
          <ProductSteps onOpen={setLightboxIndex} />
        </div>
      </section>

      {lightboxIndex !== null && (
        <Lightbox shot={STEPS[lightboxIndex]} onClose={() => setLightboxIndex(null)} />
      )}

      <div className={styles.disclaimer}>
        <div className={styles.wrap}>
          <p>
            TickerThesis is an AI-generated research aid, not financial advice. All content should be
            independently verified.
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
