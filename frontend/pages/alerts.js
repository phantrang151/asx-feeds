import { useEffect, useMemo, useState } from 'react';
import Navbar from '../components/Navbar';
import { useRequireAuth } from '../hooks/useRequireAuth';
import { supabase } from '../lib/supabaseClient';

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export default function Alerts() {
  const { user, loading } = useRequireAuth();
  const [items, setItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(true);

  const [ticker, setTicker] = useState('all');
  const [year, setYear] = useState('all');
  const [month, setMonth] = useState('all');
  const [date, setDate] = useState('');

  useEffect(() => {
    if (!user) return;

    supabase
      .from('feed_items')
      .select('*, feeds(feed_name, ticker)')
      .order('created_at', { ascending: false })
      .then(({ data, error }) => {
        if (!error) setItems(data);
        setLoadingItems(false);
      });
  }, [user]);

  const tickers = useMemo(() => {
    const set = new Set(items.map((i) => i.feeds?.ticker).filter(Boolean));
    return Array.from(set).sort();
  }, [items]);

  const years = useMemo(() => {
    const set = new Set(items.map((i) => new Date(i.created_at).getFullYear()));
    return Array.from(set).sort((a, b) => b - a);
  }, [items]);

  const filtered = useMemo(() => {
    return items.filter((item) => {
      if (ticker !== 'all' && item.feeds?.ticker !== ticker) return false;

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
      const key = item.feeds?.ticker || 'Unknown';
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
                <ul className="alerts-list">
                  {tickerItems.map((item) => (
                    <li key={item.id}>
                      <span className="alert-feed">{item.feeds?.feed_name}</span>
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
