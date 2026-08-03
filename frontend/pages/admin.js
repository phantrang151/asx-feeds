import { useEffect, useState } from 'react';
import Navbar from '../components/Navbar';
import { useRequireAuth } from '../hooks/useRequireAuth';
import { supabase } from '../lib/supabaseClient';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const ASX_TICKER_PATTERN = /^[A-Z0-9]{1,6}\.AX$/;

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

async function authedFetchMultipart(path, formData) {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return fetch(`${API_URL}${path}`, {
    method: 'POST',
    // No Content-Type here - fetch sets multipart/form-data with the right boundary
    // itself for a FormData body; authedFetch's hardcoded JSON header would break that.
    headers: { Authorization: `Bearer ${session.access_token}` },
    body: formData,
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

  const [generationRuns, setGenerationRuns] = useState([]);
  const [classificationRuns, setClassificationRuns] = useState([]);
  const [triggeringEval, setTriggeringEval] = useState(false);
  const [evalError, setEvalError] = useState('');

  const [docTicker, setDocTicker] = useState('');
  const [docTickerError, setDocTickerError] = useState('');
  const [docFiles, setDocFiles] = useState(null);
  const [docLinks, setDocLinks] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState(null);
  const [documents, setDocuments] = useState(null);

  async function loadDocuments(ticker) {
    const res = await authedFetch(`/api/admin/documents?ticker=${encodeURIComponent(ticker)}`);
    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    setDocuments(await res.json());
  }

  function handleViewDocuments() {
    setDocTickerError('');
    const ticker = docTicker.trim().toUpperCase();
    if (!ASX_TICKER_PATTERN.test(ticker)) {
      setDocTickerError('Ticker must be a Yahoo Finance ASX symbol, e.g. TLS.AX.');
      return;
    }
    loadDocuments(ticker);
  }

  async function handleUploadDocuments(e) {
    e.preventDefault();
    setDocTickerError('');
    setUploadResults(null);

    const ticker = docTicker.trim().toUpperCase();
    if (!ASX_TICKER_PATTERN.test(ticker)) {
      setDocTickerError('Ticker must be a Yahoo Finance ASX symbol, e.g. TLS.AX.');
      return;
    }

    const formData = new FormData();
    formData.append('ticker', ticker);
    formData.append('links', docLinks);
    for (const file of docFiles || []) {
      formData.append('files', file);
    }

    setUploading(true);
    const res = await authedFetchMultipart('/api/admin/documents/upload', formData);
    setUploading(false);

    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setDocTickerError(body.detail || 'Upload failed.');
      return;
    }

    const data = await res.json();
    setUploadResults(data.results);
    setDocFiles(null);
    setDocLinks('');
    loadDocuments(ticker);
  }

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

  async function loadEvalRuns() {
    const [genRes, classRes] = await Promise.all([
      authedFetch('/api/admin/eval/runs?eval_type=generation'),
      authedFetch('/api/admin/eval/runs?eval_type=classification'),
    ]);
    if (genRes.status === 403 || classRes.status === 403) {
      setForbidden(true);
      return;
    }
    setGenerationRuns(await genRes.json());
    setClassificationRuns(await classRes.json());
  }

  async function handleTriggerGenerationEval() {
    setTriggeringEval(true);
    setEvalError('');
    const res = await authedFetch('/api/admin/eval/generation/trigger', { method: 'POST' });
    setTriggeringEval(false);

    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setEvalError(body.detail || 'Failed to run the generation eval.');
      return;
    }
    loadEvalRuns();
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
      loadEvalRuns();
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
          <h2>Upload financial reports</h2>
          <form onSubmit={handleUploadDocuments} className="stacked-form">
            <label>
              Ticker
              <input
                value={docTicker}
                onChange={(e) => setDocTicker(e.target.value)}
                placeholder="e.g. TLS.AX"
                required
              />
            </label>
            <label>
              Files
              <input type="file" multiple onChange={(e) => setDocFiles(e.target.files)} />
            </label>
            <label>
              Links (one per line)
              <textarea
                value={docLinks}
                onChange={(e) => setDocLinks(e.target.value)}
                rows={3}
                placeholder={'https://example.com/annual-report.pdf'}
              />
            </label>
            <div className="feed-edit-actions">
              <button type="submit" disabled={uploading}>
                {uploading ? 'Uploading...' : 'Upload'}
              </button>
              <button type="button" onClick={handleViewDocuments}>
                View documents for this ticker
              </button>
            </div>
            {docTickerError && <p className="error">{docTickerError}</p>}
          </form>

          {uploadResults && (
            <ul className="admin-runs">
              {uploadResults.map((r, i) => (
                <li key={i}>
                  <strong>{r.status === 'ready' ? 'Ready' : 'Failed'}</strong> - {r.title}
                  {r.status === 'ready' ? ` (${r.chunk_count} chunks)` : ` - ${r.error}`}
                </li>
              ))}
            </ul>
          )}

          {documents && (
            <>
              <h3>Documents for {docTicker.trim().toUpperCase()}</h3>
              {documents.length === 0 ? (
                <p>No documents uploaded for this ticker yet.</p>
              ) : (
                <ul className="admin-runs">
                  {documents.map((d) => (
                    <li key={d.id}>
                      <strong>{d.status}</strong> - {d.title} ({d.source_type}, {d.chunk_count} chunks) -{' '}
                      {new Date(d.created_at).toLocaleString()}
                      {d.error && ` - ${d.error}`}
                    </li>
                  ))}
                </ul>
              )}
            </>
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
            Cost/latency/error rate only - model quality metrics (groundedness, relevance,
            advice-avoidance, classification precision/recall) are in the Evaluation section below.
          </p>
        </section>

        <section>
          <h2>Evaluation</h2>

          <h3>Generation quality (LLM-judge)</h3>
          <p className="info">
            Judges conduct_analysis answers on a fixed question set for groundedness (is every
            claim backed by the evidence?), relevance, and advice-avoidance. Makes real, live LLM
            calls - not free, not instant, and subject to the same daily model quota as normal chat
            traffic.
          </p>
          <button onClick={handleTriggerGenerationEval} disabled={triggeringEval}>
            {triggeringEval ? 'Running generation eval...' : 'Run generation eval now'}
          </button>
          {evalError && <p className="error">{evalError}</p>}

          {generationRuns.length === 0 ? (
            <p>No generation eval runs yet.</p>
          ) : (
            <ul className="admin-runs">
              {generationRuns.map((r) => (
                <li key={r.id}>
                  {new Date(r.created_at).toLocaleString()} - avg relevance{' '}
                  {r.summary.summary.avg_relevance ?? 'n/a'}/5, {r.summary.summary.pct_grounded ?? 'n/a'}%
                  grounded, {r.summary.summary.pct_advice_avoidance_passed ?? 'n/a'}% advice-avoidance
                  pass ({r.summary.summary.n_judged}/{r.summary.summary.n_total} judged)
                </li>
              ))}
            </ul>
          )}

          <h3>Classification quality (news &rarr; feed)</h3>
          <p className="info">
            Measures precision/recall/false-skip-rate of common-feed classification against a
            hand-labeled sample - not triggerable from here, since it needs a human to label real
            examples first: run <code>python -m eval.export_labels</code>, fill in the
            <code>correct_feed</code> column, then{' '}
            <code>python -m eval.score_classification --labels &lt;file&gt;</code> to add a run here.
          </p>
          {classificationRuns.length === 0 ? (
            <p>No classification eval runs yet.</p>
          ) : (
            <ul className="admin-runs">
              {classificationRuns.map((r) => (
                <li key={r.id}>
                  {new Date(r.created_at).toLocaleString()}
                  <ul>
                    {r.summary.results.map((res, i) => (
                      <li key={i}>
                        threshold {res.threshold} (n={res.n}): precision {res.precision ?? 'n/a'}, recall{' '}
                        {res.recall ?? 'n/a'}, false-skip rate {res.false_skip_rate ?? 'n/a'}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
