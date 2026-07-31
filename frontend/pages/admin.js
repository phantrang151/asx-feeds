import { useEffect, useState } from 'react';
import Navbar from '../components/Navbar';
import { useRequireAuth } from '../hooks/useRequireAuth';
import { supabase } from '../lib/supabaseClient';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function authedFetch(path, options = {}) {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${session.access_token}`,
      ...(options.headers || {}),
    },
  });
}

export default function Admin() {
  const { user, loading } = useRequireAuth();
  const [forbidden, setForbidden] = useState(false);
  const [runs, setRuns] = useState([]);
  const [summary, setSummary] = useState(null);
  const [triggering, setTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState(null);
  const [error, setError] = useState('');

  async function loadRuns() {
    const res = await authedFetch('/api/admin/pipeline/runs');
    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    setRuns(await res.json());
  }

  async function loadSummary() {
    const res = await authedFetch('/api/admin/langsmith/summary');
    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    setSummary(await res.json());
  }

  async function handleTrigger() {
    setTriggering(true);
    setError('');
    const res = await authedFetch('/api/admin/pipeline/trigger', { method: 'POST' });
    setTriggering(false);

    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (!res.ok) {
      setError('Failed to trigger the pipeline.');
      return;
    }
    setTriggerResult(await res.json());
    loadRuns();
  }

  useEffect(() => {
    if (user) {
      loadRuns();
      loadSummary();
    }
  }, [user]);

  if (loading || !user) {
    return <p style={{ textAlign: 'center', marginTop: 80 }}>Loading...</p>;
  }

  if (forbidden) {
    return (
      <div>
        <Navbar />
        <main className="container">
          <section>
            <p>Admin access only.</p>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div>
      <Navbar />
      <main className="container">
        <section>
          <h2>Pipeline control</h2>
          <button onClick={handleTrigger} disabled={triggering}>
            {triggering ? 'Running ingestion...' : 'Trigger ingestion now'}
          </button>
          {error && <p className="error">{error}</p>}
          {triggerResult && (
            <p className="info">
              Run finished: {triggerResult.status} - {triggerResult.feeds_classified} custom,{' '}
              {triggerResult.common_items_classified} common classified,{' '}
              {triggerResult.items_skipped} skipped, {triggerResult.errors.length} errors across{' '}
              {triggerResult.tickers_processed} tickers.
            </p>
          )}
        </section>

        <section>
          <h2>Recent pipeline runs</h2>
          {runs.length === 0 ? (
            <p>No runs yet.</p>
          ) : (
            <ul className="admin-runs">
              {runs.map((r) => (
                <li key={r.id}>
                  <strong>{r.status}</strong> - {new Date(r.started_at).toLocaleString()} -{' '}
                  {r.feeds_classified} custom, {r.common_items_classified} common classified,{' '}
                  {r.items_skipped} skipped, {(r.errors || []).length} errors ({r.tickers_processed} tickers)
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h2>Model monitoring (last 24h)</h2>
          {!summary ? (
            <p>Loading...</p>
          ) : summary.run_count === 0 ? (
            <p>
              No LangSmith traces found - confirm LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY
              are set in the backend .env.
            </p>
          ) : (
            <ul className="admin-runs">
              <li>Traced runs: {summary.run_count}</li>
              <li>Errors: {summary.error_count}</li>
              <li>Avg latency: {summary.avg_latency_seconds ?? 'n/a'}s</li>
              <li>Total tokens: {summary.total_tokens}</li>
              <li>
                Estimated cost:{' '}
                {summary.estimated_cost_usd != null ? `$${summary.estimated_cost_usd}` : 'n/a'}
              </li>
            </ul>
          )}
          <p className="info">
            Model quality metrics (accuracy, relevance, groundedness, etc.) aren&apos;t defined
            yet - this section covers cost/latency/error rate only until those are decided.
          </p>
        </section>
      </main>
    </div>
  );
}
