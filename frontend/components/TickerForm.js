import { useState } from 'react';
import { supabase } from '../lib/supabaseClient';

// Yahoo Finance's symbol format for ASX-listed stocks - what tools/search.py's
// yf.Ticker() call needs to actually find news. A ticker stored in any other shape
// (e.g. "ASX: TLS") silently returns zero news results with no error, so it's enforced
// at entry time here rather than failing invisibly deep in the ingestion pipeline.
const ASX_TICKER_PATTERN = /^[A-Z0-9]{1,6}\.AX$/;

export default function TickerForm({ onAdded }) {
  const [ticker, setTicker] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    const normalized = ticker.trim().toUpperCase();
    if (!ASX_TICKER_PATTERN.test(normalized)) {
      setError('Ticker must be a Yahoo Finance ASX symbol, e.g. TLS.AX.');
      return;
    }

    const {
      data: { user },
    } = await supabase.auth.getUser();

    const { error } = await supabase.from('watchlist_stocks').insert({
      user_id: user.id,
      ticker: normalized,
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
