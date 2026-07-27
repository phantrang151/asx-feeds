import { useEffect, useState } from 'react';
import Navbar from '../components/Navbar';
import TickerForm from '../components/TickerForm';
import TickerList from '../components/TickerList';
import FeedForm from '../components/FeedForm';
import FeedList from '../components/FeedList';
import { useRequireAuth } from '../hooks/useRequireAuth';
import { supabase } from '../lib/supabaseClient';

export default function Dashboard() {
  const { user, loading } = useRequireAuth();
  const [tickers, setTickers] = useState([]);
  const [feeds, setFeeds] = useState([]);

  async function loadTickers() {
    const { data, error } = await supabase
      .from('watchlist_stocks')
      .select('*')
      .order('created_at', { ascending: false });
    if (!error) setTickers(data);
  }

  async function loadFeeds() {
    const { data, error } = await supabase
      .from('feeds')
      .select('*')
      .order('created_at', { ascending: false });
    if (!error) setFeeds(data);
  }

  useEffect(() => {
    if (user) {
      loadTickers();
      loadFeeds();
    }
  }, [user]);

  if (loading || !user) {
    return <p style={{ textAlign: 'center', marginTop: 80 }}>Loading...</p>;
  }

  return (
    <div>
      <Navbar />
      <main className="container">
        <section>
          <h2>Your tickers</h2>
          <TickerForm onAdded={loadTickers} />
          <TickerList tickers={tickers} />
        </section>

        <section>
          <h2>Your feeds</h2>
          <FeedForm tickers={tickers} onCreated={loadFeeds} />
          <FeedList feeds={feeds} />
        </section>
      </main>
    </div>
  );
}
