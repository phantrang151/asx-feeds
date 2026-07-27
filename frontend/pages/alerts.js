import { useEffect, useState } from 'react';
import Navbar from '../components/Navbar';
import { useRequireAuth } from '../hooks/useRequireAuth';
import { supabase } from '../lib/supabaseClient';

export default function Alerts() {
  const { user, loading } = useRequireAuth();
  const [items, setItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(true);

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

  if (loading || !user) {
    return <p style={{ textAlign: 'center', marginTop: 80 }}>Loading...</p>;
  }

  return (
    <div>
      <Navbar />
      <main className="container">
        <section>
          <h2>Alerts</h2>
          {loadingItems ? (
            <p>Loading alerts...</p>
          ) : items.length === 0 ? (
            <p>No alerts yet - once the daily pipeline runs, classified news will show up here.</p>
          ) : (
            <ul className="alerts-list">
              {items.map((item) => (
                <li key={item.id}>
                  <span className="alert-feed">
                    {item.feeds?.feed_name} ({item.feeds?.ticker})
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
          )}
        </section>
      </main>
    </div>
  );
}
