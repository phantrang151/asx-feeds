import { useEffect, useState } from 'react';
import Navbar from '../components/Navbar';
import TickerForm from '../components/TickerForm';
import FeedForm from '../components/FeedForm';
import TickerFeedsList from '../components/TickerFeedsList';
import AskQuestion from '../components/AskQuestion';
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
          <h2>Ask a question</h2>
          <AskQuestion />
        </section>

        <div className="dashboard-grid">
          <div className="dashboard-col">
            <section>
              <h2>Add a ticker</h2>
              <TickerForm onAdded={loadTickers} />
            </section>

            <section>
              <h2>Create a feed</h2>
              <FeedForm tickers={tickers} onCreated={loadFeeds} />
            </section>
          </div>

          <div className="dashboard-col">
            <section>
              <h2>Your tickers &amp; feeds</h2>
              <TickerFeedsList tickers={tickers} feeds={feeds} />
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
