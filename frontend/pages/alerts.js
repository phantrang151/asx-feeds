import { useEffect, useMemo, useState } from 'react';
import Navbar from '../components/Navbar';
import { useRequireAuth } from '../hooks/useRequireAuth';
import { supabase } from '../lib/supabaseClient';

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function InsightCard({ insight, tickerItems, feedNames, itemsById }) {
  if (!insight) return null;

  const sourceIds = insight.based_on_feed_item_ids || [];
  const feedSummaries = insight.feed_summaries || [];

  // feed_summaries is '[]' on insights generated before per-feed sufficiency gating shipped
  // (schema.sql's column default) - fall back to the old client-side count-only tags so
  // those older insights don't silently lose their tag row.
  const tagCounts =
    feedSummaries.length > 0
      ? feedSummaries.map((fs) => ({
          name: fs.feed_name,
          label: fs.status === 'insufficient' ? 'not enough evidence' : fs.item_count,
          muted: fs.status === 'insufficient',
        }))
      : feedNames.map((name) => {
          const count = tickerItems.filter((item) => item.feed_name === name).length;
          return { name, label: count, muted: count === 0 };
        });

  const perFeedSummaries = feedSummaries.filter((fs) => fs.status === 'sufficient');

  return (
    <div className="insight-card">
      <div className="insight-head">
        <span className="insight-badge">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 0l2.2 7.6L22 10l-7.8 2.4L12 20l-2.2-7.6L2 10l7.8-2.4z" />
          </svg>
          Cross-feed insight
        </span>
        <span className="insight-meta">{new Date(insight.created_at).toLocaleDateString()}</span>
      </div>
      <p className="insight-text">{insight.insight_text}</p>
      <div className="insight-foot">
        {tagCounts.length > 0 && (
          <div className="tags">
            {tagCounts.map(({ name, label, muted }) => (
              <span key={name} className={muted ? 'tag muted' : 'tag'}>
                {name} · {label}
              </span>
            ))}
          </div>
        )}
        {sourceIds.length > 0 && (
          <details className="insight-sources">
            <summary>{sourceIds.length} sources</summary>
            <ul>
              {sourceIds.map((id) => {
                const src = itemsById.get(id);
                if (!src) return null;
                return (
                  <li key={id}>
                    {src.source_url ? (
                      <a href={src.source_url} target="_blank" rel="noreferrer">
                        {src.content_summary}
                      </a>
                    ) : (
                      src.content_summary
                    )}{' '}
                    — {src.feed_name}
                  </li>
                );
              })}
            </ul>
          </details>
        )}
        {perFeedSummaries.length > 0 && (
          <details className="insight-sources">
            <summary>Per-feed summaries</summary>
            <ul>
              {perFeedSummaries.map((fs) => (
                <li key={fs.feed_name}>
                  <strong>{fs.feed_name}:</strong> {fs.summary}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}

export default function Alerts() {
  const { user, loading } = useRequireAuth();
  const [items, setItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(true);
  const [insights, setInsights] = useState([]);
  const [feeds, setFeeds] = useState([]);

  const [ticker, setTicker] = useState('all');
  const [year, setYear] = useState('all');
  const [month, setMonth] = useState('all');
  const [date, setDate] = useState('');

  useEffect(() => {
    if (!user) return;

    // user_feed_items is a view unioning per-user feed_items (custom feeds) with the
    // shared common_feed_items (common feeds) - see schema.sql. It has no FK for
    // PostgREST to embed through, so feed_name/ticker come back as flat columns here
    // instead of a nested `feeds` relation.
    supabase
      .from('user_feed_items')
      .select('*')
      .order('created_at', { ascending: false })
      .then(({ data, error }) => {
        if (!error) setItems(data);
        setLoadingItems(false);
      });

    // ticker_insights holds insight_graph's cross-feed summary, one row per synthesis
    // run - RLS ("select own insights") already scopes this to the signed-in user.
    supabase
      .from('ticker_insights')
      .select('*')
      .order('created_at', { ascending: false })
      .then(({ data, error }) => {
        if (!error) setInsights(data);
      });

    // feeds (not user_feed_items) so a feed with zero matching items this period still
    // shows up as a "· 0" tag on the insight card, instead of silently disappearing.
    supabase
      .from('feeds')
      .select('*')
      .then(({ data, error }) => {
        if (!error) setFeeds(data);
      });
  }, [user]);

  // Only the most recent insight per ticker is shown - older ones stay in the table
  // as history but aren't surfaced here.
  const latestInsightByTicker = useMemo(() => {
    const map = new Map();
    for (const insight of insights) {
      if (!map.has(insight.ticker)) map.set(insight.ticker, insight);
    }
    return map;
  }, [insights]);

  const itemsById = useMemo(() => {
    const map = new Map();
    for (const item of items) map.set(item.id, item);
    return map;
  }, [items]);

  const feedNamesByTicker = useMemo(() => {
    const map = new Map();
    for (const feed of feeds) {
      if (!map.has(feed.ticker)) map.set(feed.ticker, []);
      map.get(feed.ticker).push(feed.feed_name);
    }
    return map;
  }, [feeds]);

  const tickers = useMemo(() => {
    const set = new Set(items.map((i) => i.ticker).filter(Boolean));
    return Array.from(set).sort();
  }, [items]);

  const years = useMemo(() => {
    const set = new Set(items.map((i) => new Date(i.created_at).getFullYear()));
    return Array.from(set).sort((a, b) => b - a);
  }, [items]);

  const filtered = useMemo(() => {
    return items.filter((item) => {
      if (ticker !== 'all' && item.ticker !== ticker) return false;

      const created = new Date(item.created_at);

      // An exact date pins the day - month/year filters are ignored while it's set
      // (see the disabled selects below), so they're only checked in the else branch.
      if (date) {
        return created.toISOString().slice(0, 10) === date;
      }

      if (year !== 'all' && created.getFullYear() !== Number(year)) return false;
      if (month !== 'all' && created.getMonth() + 1 !== Number(month)) return false;

      return true;
    });
  }, [items, ticker, year, month, date]);

  const grouped = useMemo(() => {
    const map = new Map();
    for (const item of filtered) {
      const key = item.ticker || 'Unknown';
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(item);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filtered]);

  function clearFilters() {
    setTicker('all');
    setYear('all');
    setMonth('all');
    setDate('');
  }

  if (loading || !user) {
    return <p style={{ textAlign: 'center', marginTop: 80 }}>Loading...</p>;
  }

  return (
    <div>
      <Navbar />
      <main className="container">
        <section>
          <h2>Alerts</h2>

          <div className="alerts-filters">
            <label>
              Ticker
              <select value={ticker} onChange={(e) => setTicker(e.target.value)}>
                <option value="all">All</option>
                {tickers.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Year
              <select value={year} onChange={(e) => setYear(e.target.value)} disabled={!!date}>
                <option value="all">All</option>
                {years.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Month
              <select value={month} onChange={(e) => setMonth(e.target.value)} disabled={!!date}>
                <option value="all">All</option>
                {MONTHS.map((m, i) => (
                  <option key={m} value={i + 1}>
                    {m}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Exact date
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </label>

            <button type="button" onClick={clearFilters}>
              Clear filters
            </button>
          </div>

          {loadingItems ? (
            <p>Loading alerts...</p>
          ) : grouped.length === 0 ? (
            <p>No alerts match these filters.</p>
          ) : (
            grouped.map(([tickerKey, tickerItems]) => (
              <div key={tickerKey} className="alerts-group">
                <h3>{tickerKey}</h3>
                <InsightCard
                  insight={latestInsightByTicker.get(tickerKey)}
                  tickerItems={tickerItems}
                  feedNames={feedNamesByTicker.get(tickerKey) || []}
                  itemsById={itemsById}
                />
                <ul className="alerts-list">
                  {tickerItems.map((item) => (
                    <li key={item.id}>
                      <span className="alert-feed">{item.feed_name}</span>
                      <span className="alert-date">
                        {new Date(item.created_at).toLocaleDateString()}
                      </span>
                      <p>{item.content_summary}</p>
                      {item.source_url && (
                        <a href={item.source_url} target="_blank" rel="noreferrer">
                          Source
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </section>
      </main>
    </div>
  );
}
