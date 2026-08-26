import { useState } from 'react';
import { supabase } from '../lib/supabaseClient';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function TickerForm({ onAdded }) {
  const [ticker, setTicker] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    const normalized = ticker.trim().toUpperCase();
    const {
      data: { session },
    } = await supabase.auth.getSession();

    const res = await fetch(`${API_URL}/api/tickers`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ ticker: normalized, company_name: companyName }),
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(body.detail || 'Failed to add ticker.');
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
