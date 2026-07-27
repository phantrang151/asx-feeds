import { useState } from 'react';
import { supabase } from '../lib/supabaseClient';

export default function TickerForm({ onAdded }) {
  const [ticker, setTicker] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    const {
      data: { user },
    } = await supabase.auth.getUser();

    const { error } = await supabase.from('watchlist_stocks').insert({
      user_id: user.id,
      ticker: ticker.toUpperCase(),
      company_name: companyName,
    });

    if (error) {
      setError(error.message);
      return;
    }

    setTicker('');
    setCompanyName('');
    onAdded();
  }

  return (
    <form onSubmit={handleSubmit} className="inline-form">
      <input
        placeholder="Ticker (e.g. TLS.AX)"
        value={ticker}
        onChange={(e) => setTicker(e.target.value)}
        required
      />
      <input
        placeholder="Company name"
        value={companyName}
        onChange={(e) => setCompanyName(e.target.value)}
        required
      />
      <button type="submit">Add ticker</button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
