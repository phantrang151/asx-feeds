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

  const [guardrailRuns, setGuardrailRuns] = useState([]);
  const [triggeringGuardrailEval, setTriggeringGuardrailEval] = useState(false);
  const [guardrailEvalError, setGuardrailEvalError] = useState('');

  const [liveSampleRuns, setLiveSampleRuns] = useState([]);
  const [triggeringLiveSampleEval, setTriggeringLiveSampleEval] = useState(false);
  const [liveSampleEvalError, setLiveSampleEvalError] = useState('');

  const [efficiency, setEfficiency] = useState(null);
  const [alerts, setAlerts] = useState([]);

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
    const [genRes, classRes, guardrailRes, liveSampleRes] = await Promise.all([
      authedFetch('/api/admin/eval/runs?eval_type=generation'),
      authedFetch('/api/admin/eval/runs?eval_type=classification'),
      authedFetch('/api/admin/eval/runs?eval_type=guardrails'),
      authedFetch('/api/admin/eval/runs?eval_type=live_sample'),
    ]);
    if ([genRes, classRes, guardrailRes, liveSampleRes].some((r) => r.status === 403)) {
      setForbidden(true);
      return;
    }
    setGenerationRuns(await genRes.json());
    setClassificationRuns(await classRes.json());
    setGuardrailRuns(await guardrailRes.json());
    setLiveSampleRuns(await liveSampleRes.json());
  }

  async function loadEfficiency() {
    const res = await authedFetch('/api/admin/efficiency/summary');
    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    setEfficiency(await res.json());
  }

  async function loadAlerts() {
    const res = await authedFetch('/api/admin/alerts/recent');
    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    setAlerts(await res.json());
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

  async function handleTriggerGuardrailEval() {
    setTriggeringGuardrailEval(true);
    setGuardrailEvalError('');
    const res = await authedFetch('/api/admin/eval/guardrails/trigger', { method: 'POST' });
    setTriggeringGuardrailEval(false);

    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setGuardrailEvalError(body.detail || 'Failed to run the guardrail eval.');
      return;
    }
    loadEvalRuns();
  }

  async function handleTriggerLiveSampleEval() {
    setTriggeringLiveSampleEval(true);
    setLiveSampleEvalError('');
    const res = await authedFetch('/api/admin/eval/live-sample/trigger', { method: 'POST' });
    setTriggeringLiveSampleEval(false);

    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setLiveSampleEvalError(body.detail || 'Failed to run the live-sample eval.');
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
      loadEfficiency();
      loadAlerts();
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
                  pass, {r.summary.summary.pct_answer_found ?? 'n/a'}% answer found (recall) (
                  {r.summary.summary.n_judged}/{r.summary.summary.n_total} judged)
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

          <h3>Guardrail effectiveness (input &amp; output, per layer)</h3>
          <p className="info">
            True-positive rate (catches real bad questions/answers) and false-positive rate (wrongly
            blocks legitimate ones), scored independently for each guardrail&apos;s regex layer and LLM
            layer against a small hand-labeled test set - shows whether the cheap regex layer is
            pulling its weight or the LLM layer is doing all the real work. Grow{' '}
            <code>eval/fixtures/input_guardrail_test_set.json</code> and{' '}
            <code>output_guardrail_test_set.json</code> over time, the same way the classification
            worksheet grows.
          </p>
          <button onClick={handleTriggerGuardrailEval} disabled={triggeringGuardrailEval}>
            {triggeringGuardrailEval ? 'Running guardrail eval...' : 'Run guardrail eval now'}
          </button>
          {guardrailEvalError && <p className="error">{guardrailEvalError}</p>}

          {guardrailRuns.length === 0 ? (
            <p>No guardrail eval runs yet.</p>
          ) : (
            <ul className="admin-runs">
              {guardrailRuns.map((r) => (
                <li key={r.id}>
                  {new Date(r.created_at).toLocaleString()}
                  <ul>
                    <li>
                      Input guardrail - regex: TPR {r.summary.summary.input_guardrail.regex_layer.true_positive_rate ?? 'n/a'},
                      FPR {r.summary.summary.input_guardrail.regex_layer.false_positive_rate ?? 'n/a'}; llm: TPR{' '}
                      {r.summary.summary.input_guardrail.llm_layer.true_positive_rate ?? 'n/a'}, FPR{' '}
                      {r.summary.summary.input_guardrail.llm_layer.false_positive_rate ?? 'n/a'}
                    </li>
                    <li>
                      Output guardrail - regex: TPR {r.summary.summary.output_guardrail.regex_layer.true_positive_rate ?? 'n/a'},
                      FPR {r.summary.summary.output_guardrail.regex_layer.false_positive_rate ?? 'n/a'}; llm: TPR{' '}
                      {r.summary.summary.output_guardrail.llm_layer.true_positive_rate ?? 'n/a'}, FPR{' '}
                      {r.summary.summary.output_guardrail.llm_layer.false_positive_rate ?? 'n/a'}
                    </li>
                  </ul>
                </li>
              ))}
            </ul>
          )}

          <h3>Continuous monitoring (random live-traffic sample)</h3>
          <p className="info">
            Judges a random sample of real recent conduct_analysis requests (not a fixed fixture set)
            for groundedness, relevance, and answer-discovery - a small fixed sample size (10/day by
            default) keeps judging cost predictable regardless of how much real traffic there is.
          </p>
          <button onClick={handleTriggerLiveSampleEval} disabled={triggeringLiveSampleEval}>
            {triggeringLiveSampleEval ? 'Running live-sample eval...' : 'Run live-sample eval now'}
          </button>
          {liveSampleEvalError && <p className="error">{liveSampleEvalError}</p>}

          {liveSampleRuns.length === 0 ? (
            <p>No live-sample eval runs yet.</p>
          ) : (
            <ul className="admin-runs">
              {liveSampleRuns.map((r) => (
                <li key={r.id}>
                  {new Date(r.created_at).toLocaleString()} - sampled {r.summary.summary.n_sampled}, avg
                  relevance {r.summary.summary.avg_relevance ?? 'n/a'}/5, {r.summary.summary.pct_grounded ?? 'n/a'}%
                  grounded, {r.summary.summary.pct_answer_found ?? 'n/a'}% answer found
                </li>
              ))}
            </ul>
          )}

          <h3>Efficiency &amp; cost (last 7 days)</h3>
          <p className="info">
            Steps/tokens/latency percentiles across recent requests - what config.py&apos;s guardrail
            ceilings (REACT_RECURSION_LIMIT, TOKEN_CEILING_PER_REQUEST) should eventually be retuned
            against, once there&apos;s a real p95/max to look at instead of a placeholder.
          </p>
          <button onClick={loadEfficiency}>Refresh</button>
          {!efficiency ? (
            <p>Loading...</p>
          ) : efficiency.n === 0 ? (
            <p>No requests in this window yet.</p>
          ) : (
            <ul className="admin-runs">
              <li>Requests: {efficiency.n}</li>
              <li>
                Steps (tool calls) - p50 {efficiency.steps.p50 ?? 'n/a'}, p95 {efficiency.steps.p95 ?? 'n/a'}, max{' '}
                {efficiency.steps.max ?? 'n/a'}
              </li>
              <li>
                Tokens - p50 {efficiency.tokens.p50 ?? 'n/a'}, p95 {efficiency.tokens.p95 ?? 'n/a'}, max{' '}
                {efficiency.tokens.max ?? 'n/a'}
              </li>
              <li>
                Latency (ms) - p50 {efficiency.duration_ms.p50 ?? 'n/a'}, p95 {efficiency.duration_ms.p95 ?? 'n/a'}, max{' '}
                {efficiency.duration_ms.max ?? 'n/a'}
              </li>
              <li>Recursion-limit hit rate: {efficiency.recursion_limit_hit_rate ?? 'n/a'}</li>
            </ul>
          )}

          <h3>Alerts</h3>
          <p className="info">
            Fires when a request&apos;s cost, latency, or step count crosses a configured threshold (see
            config.py&apos;s ALERT_* constants) - cost/step-count alerts fire at the same value their
            matching hard guardrail already blocks at; latency (&gt;30s) has no matching guardrail, so
            it&apos;s a pure early-warning signal.
          </p>
          <button onClick={loadAlerts}>Refresh</button>
          {alerts.length === 0 ? (
            <p>No alerts yet.</p>
          ) : (
            <ul className="admin-runs">
              {alerts.map((a) => (
                <li key={a.id}>
                  {new Date(a.created_at).toLocaleString()} - <strong>{a.alert_type}</strong>: {a.actual_value} (threshold{' '}
                  {a.threshold})
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
