import { useState } from 'react';
import { supabase } from '../lib/supabaseClient';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function FeedForm({ tickers, onCreated }) {
  const [ticker, setTicker] = useState('');
  const [feedName, setFeedName] = useState('');
  const [feedDescription, setFeedDescription] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    const {
      data: { session },
    } = await supabase.auth.getSession();

    let res;
    try {
      res = await fetch(`${API_URL}/api/feeds`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          ticker,
          feed_name: feedName,
          feed_description: feedDescription,
        }),
      });
    } catch (err) {
      setSubmitting(false);
      setError('Could not reach the API - is it running on ' + API_URL + '?');
      return;
    }

    setSubmitting(false);

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(body.detail || 'Failed to create feed.');
      return;
    }

    setFeedName('');
    setFeedDescription('');
    onCreated();
  }

  return (
    <form onSubmit={handleSubmit} className="stacked-form">
      <label>
        Ticker
        <select value={ticker} onChange={(e) => setTicker(e.target.value)} required>
          <option value="" disabled>
            Select a ticker
          </option>
          {tickers.map((t) => (
            <option key={t.id} value={t.ticker}>
              {t.ticker}
            </option>
          ))}
        </select>
      </label>
      <label>
        Feed name
        <input value={feedName} onChange={(e) => setFeedName(e.target.value)} required />
      </label>
      <label>
        Feed description
        <textarea
          value={feedDescription}
          onChange={(e) => setFeedDescription(e.target.value)}
          required
          rows={3}
          placeholder="e.g. News and signals about whether revenue is increasing or decreasing."
        />
      </label>
      <button type="submit" disabled={submitting || !tickers.length}>
        {submitting ? 'Creating...' : 'Create feed'}
      </button>
      {!tickers.length && <p className="info">Add a ticker first before creating a feed.</p>}
      {error && <p className="error">{error}</p>}
    </form>
  );
}
