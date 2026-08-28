import { useEffect, useState } from 'react';
import Navbar from '../components/Navbar';
import { useRequireAuth } from '../hooks/useRequireAuth';
import { supabase } from '../lib/supabaseClient';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const ASX_TICKER_PATTERN = /^[A-Z0-9]{1,6}\.AX$/;

// fetch() REJECTS (throws) on a network-level failure - backend unreachable, still
// starting up, DNS/CORS failure - as opposed to an HTTP error status, which is still a
// resolved Response with res.ok===false. Every caller below only ever branches on
// res.status/res.ok, so on a rejection this returns a fake Response shaped the same way
// instead of throwing, meaning one code path (each caller's existing res.ok check) handles
// both kinds of failure. Previously the rejection went uncaught, through both the
// useEffect loaders AND the button onClick handlers, and Next's dev overlay renders any
// uncaught error full-screen - which is what "the admin page disappears" actually was,
// triggered simply by loading this page while the backend happened to be down/restarting.
function _unreachableResponse() {
  return {
    ok: false,
    status: 0,
    json: async () => ({ detail: `Could not reach the API at ${API_URL} - is the backend running?` }),
  };
}

async function authedFetch(path, options = {}) {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  try {
    return await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${session.access_token}`,
        ...(options.headers || {}),
      },
    });
  } catch {
    return _unreachableResponse();
  }
}

async function authedFetchMultipart(path, formData) {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  try {
    return await fetch(`${API_URL}${path}`, {
      method: 'POST',
      // No Content-Type here - fetch sets multipart/form-data with the right boundary
      // itself for a FormData body; authedFetch's hardcoded JSON header would break that.
      headers: { Authorization: `Bearer ${session.access_token}` },
      body: formData,
    });
  } catch {
    return _unreachableResponse();
  }
}

// Plain inline SVG - no charting library in this project's dependencies (see
// package.json) and a ROC curve is simple enough not to need one. fpr/tpr are both
// already 0-1 (see agent/eval/score_classification.py::compute_roc_auc), so the plot
// area maps directly with no scale computation.
function RocCurve({ rocAuc }) {
  if (!rocAuc || !rocAuc.roc_points || rocAuc.roc_points.length === 0) {
    return null;
  }
  const size = 180;
  const pad = 24;
  const plot = size - pad * 2;
  const toX = (fpr) => pad + fpr * plot;
  const toY = (tpr) => pad + (1 - tpr) * plot;
  const points = rocAuc.roc_points.map((p) => `${toX(p.fpr)},${toY(p.tpr)}`).join(' ');
  const best = rocAuc.best_threshold_metrics;

  return (
    <div className="roc-chart">
      <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`ROC curve, AUC ${rocAuc.auc ?? 'n/a'}`}>
        {/* diagonal reference line = a coin-flip classifier */}
        <line x1={pad} y1={size - pad} x2={size - pad} y2={pad} stroke="#eee" strokeDasharray="3 3" />
        <line x1={pad} y1={pad} x2={pad} y2={size - pad} stroke="#ccc" />
        <line x1={pad} y1={size - pad} x2={size - pad} y2={size - pad} stroke="#ccc" />
        <polyline points={points} fill="none" stroke="var(--accent)" strokeWidth="2" />
        {best && <circle cx={toX(best.fpr)} cy={toY(best.tpr)} r="3.5" fill="#b3261e" />}
        <text x={pad} y={size - 8} fontSize="9" fill="#888">
          FPR &rarr;
        </text>
        <text x={4} y={pad - 6} fontSize="9" fill="#888">
          TPR
        </text>
      </svg>
      <p className="info">
        AUC {rocAuc.auc ?? 'n/a'}
        {rocAuc.best_threshold != null &&
          ` – best threshold (Youden's J) ${rocAuc.best_threshold} (red dot: tpr=${best?.tpr ?? 'n/a'}, fpr=${best?.fpr ?? 'n/a'})`}
      </p>
    </div>
  );
}

export default function Admin() {
  const { user, loading } = useRequireAuth();
  const [forbidden, setForbidden] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [runs, setRuns] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [metricsWindow, setMetricsWindow] = useState('24h');
  const [metricsStart, setMetricsStart] = useState('');
  const [metricsEnd, setMetricsEnd] = useState('');
  const [metricsError, setMetricsError] = useState('');
  const [triggering, setTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState(null);
  const [error, setError] = useState('');
  const [debugTicker, setDebugTicker] = useState('');
  const [debuggingPlanner, setDebuggingPlanner] = useState(false);
  const [debugPlannerResult, setDebugPlannerResult] = useState(null);
  const [debugPlannerError, setDebugPlannerError] = useState('');

  const [generationRuns, setGenerationRuns] = useState([]);
  const [triggeringEval, setTriggeringEval] = useState(false);
  const [evalError, setEvalError] = useState('');

  const [classificationRuns, setClassificationRuns] = useState([]);
  const [triggeringClassificationEval, setTriggeringClassificationEval] = useState(false);
  const [classificationEvalError, setClassificationEvalError] = useState('');

  const [insightRuns, setInsightRuns] = useState([]);
  const [triggeringInsightEval, setTriggeringInsightEval] = useState(false);
  const [insightEvalError, setInsightEvalError] = useState('');

  const [guardrailRuns, setGuardrailRuns] = useState([]);
  const [triggeringGuardrailEval, setTriggeringGuardrailEval] = useState(false);
  const [guardrailEvalError, setGuardrailEvalError] = useState('');

  const [researchOrderRuns, setResearchOrderRuns] = useState([]);
  const [triggeringResearchOrderEval, setTriggeringResearchOrderEval] = useState(false);
  const [researchOrderEvalError, setResearchOrderEvalError] = useState('');

  const [liveSampleRuns, setLiveSampleRuns] = useState([]);
  const [triggeringLiveSampleEval, setTriggeringLiveSampleEval] = useState(false);
  const [liveSampleEvalError, setLiveSampleEvalError] = useState('');


  const [docTicker, setDocTicker] = useState('');
  const [docTickerError, setDocTickerError] = useState('');
  const [docFiles, setDocFiles] = useState(null);
  const [docLinks, setDocLinks] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState(null);
  const [documents, setDocuments] = useState(null);

  // Every read-only loader below goes through this rather than checking `res.status === 403`
  // and otherwise trusting the body - a stale/expired session token gets a 401 (see
  // app/auth.py's decode_token) and a backend hiccup gets a 500, neither of which is a 403.
  // Treating either of those bodies as real data (e.g. {detail: "..."} where an array was
  // expected) blows up the next render's .map()/.length call - a second, separate way this
  // page could go blank, on top of the raw network failures authedFetch handles above.
  // Returns null on any failure so callers can just skip the setState and leave the
  // previous (or initial, empty-array) state in place.
  async function fetchJsonOrForbidden(path, options) {
    const res = await authedFetch(path, options);
    if (res.status === 403) {
      setForbidden(true);
      return null;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setLoadError(
        body.detail ||
          `Failed to load ${path} (${res.status}). Your session may have expired - try refreshing the page.`
      );
      return null;
    }
    return res.json();
  }

  async function loadDocuments(ticker) {
    const data = await fetchJsonOrForbidden(`/api/admin/documents?ticker=${encodeURIComponent(ticker)}`);
    if (data) setDocuments(data);
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
    const data = await fetchJsonOrForbidden('/api/admin/pipeline/runs');
    if (data) setRuns(data);
  }

  async function loadEvalRuns() {
    const [genData, classData, insightData, guardrailData, researchOrderData, liveSampleData] = await Promise.all([
      fetchJsonOrForbidden('/api/admin/eval/runs?eval_type=generation'),
      fetchJsonOrForbidden('/api/admin/eval/runs?eval_type=classification'),
      fetchJsonOrForbidden('/api/admin/eval/runs?eval_type=insight_quality'),
      fetchJsonOrForbidden('/api/admin/eval/runs?eval_type=guardrails'),
      fetchJsonOrForbidden('/api/admin/eval/runs?eval_type=research_order'),
      fetchJsonOrForbidden('/api/admin/eval/runs?eval_type=live_sample'),
    ]);
    if (genData) setGenerationRuns(genData);
    if (classData) setClassificationRuns(classData);
    if (insightData) setInsightRuns(insightData);
    if (guardrailData) setGuardrailRuns(guardrailData);
    if (researchOrderData) setResearchOrderRuns(researchOrderData);
    if (liveSampleData) setLiveSampleRuns(liveSampleData);
  }

  async function loadMetrics() {
    setMetricsError('');
    const params = new URLSearchParams();
    if (metricsWindow === 'custom') {
      if (!metricsStart || !metricsEnd) {
        setMetricsError('Choose both a start and end date.');
        return;
      }
      params.set('start', new Date(`${metricsStart}T00:00:00`).toISOString());
      params.set('end', new Date(`${metricsEnd}T23:59:59.999`).toISOString());
    } else {
      params.set('hours', metricsWindow === '24h' ? '24' : metricsWindow === '7d' ? '168' : '720');
    }
    const data = await fetchJsonOrForbidden(`/api/admin/metrics/summary?${params.toString()}`);
    if (data) setMetrics(data);
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

  async function handleTriggerClassificationEval() {
    setTriggeringClassificationEval(true);
    setClassificationEvalError('');
    const res = await authedFetch('/api/admin/eval/classification/trigger', { method: 'POST' });
    setTriggeringClassificationEval(false);

    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setClassificationEvalError(
        body.detail || 'Failed to run the classification eval.'
      );
      return;
    }
    loadEvalRuns();
  }

  async function handleTriggerInsightEval() {
    setTriggeringInsightEval(true);
    setInsightEvalError('');
    const res = await authedFetch('/api/admin/eval/insight/trigger', { method: 'POST' });
    setTriggeringInsightEval(false);

    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setInsightEvalError(body.detail || 'Failed to run the insight-quality eval.');
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

  async function handleTriggerResearchOrderEval() {
    setTriggeringResearchOrderEval(true);
    setResearchOrderEvalError('');
    const res = await authedFetch('/api/admin/eval/research-order/trigger', { method: 'POST' });
    setTriggeringResearchOrderEval(false);

    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setResearchOrderEvalError(body.detail || 'Failed to run the research-order eval.');
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

  async function handleDebugPlanner(e) {
    e.preventDefault();
    const ticker = debugTicker.trim().toUpperCase();
    setDebugPlannerError('');
    setDebugPlannerResult(null);
    if (!ASX_TICKER_PATTERN.test(ticker)) {
      setDebugPlannerError('Ticker must be a Yahoo Finance ASX symbol, e.g. CBA.AX.');
      return;
    }

    setDebuggingPlanner(true);
    const res = await authedFetch(`/api/admin/pipeline/debug-planner?ticker=${encodeURIComponent(ticker)}`, {
      method: 'POST',
    });
    setDebuggingPlanner(false);

    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      setDebugPlannerError(body.detail || 'Failed to debug the planner.');
      return;
    }
    setDebugPlannerResult(body);
  }

  useEffect(() => {
    if (user) {
      loadRuns();
      loadEvalRuns();
    }
  }, [user]);

  // Separate from the loader above so picking a new preset window (24h/7d/30d) refreshes
  // metrics immediately - custom range stays manual (via the "Refresh metrics" button)
  // since auto-firing on every keystroke while typing a date would be wasteful/wrong.
  useEffect(() => {
    if (user && metricsWindow !== 'custom') {
      loadMetrics();
    }
  }, [user, metricsWindow]);

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
        {loadError && (
          <section>
            <p className="error">{loadError}</p>
          </section>
        )}
        <section>
          <h2>Pipeline control</h2>
          <button onClick={handleTrigger} disabled={triggering}>
            {triggering ? 'Running ingestion...' : 'Trigger ingestion now'}
          </button>
          {error && <p className="error">{error}</p>}
          {triggerResult && (
            <div className={triggerResult.errors.length ? 'error' : 'info'}>
              <p>
                Run finished: {triggerResult.status} - {triggerResult.feeds_classified} custom,{' '}
                {triggerResult.common_items_classified} common classified,{' '}
                {triggerResult.items_skipped} skipped, {triggerResult.insights_generated} insights
                generated, {triggerResult.errors.length} errors across {triggerResult.tickers_processed}{' '}
                tickers.
              </p>
              {triggerResult.errors.length > 0 && (
                <ul>
                  {triggerResult.errors.map((pipelineError, index) => (
                    <li key={index}>
                      {pipelineError.ticker || 'unknown ticker'} ({pipelineError.phase}):{' '}
                      {pipelineError.error}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>

        <section className="planner-debug-section">
          <h2>Planner debugging</h2>
          <form onSubmit={handleDebugPlanner} className="inline-form planner-debug-form">
            <input
              value={debugTicker}
              onChange={(e) => setDebugTicker(e.target.value)}
              placeholder="Ticker for planner debug, e.g. CBA.AX"
              aria-label="Ticker for planner debug"
              required
            />
            <button type="submit" disabled={debuggingPlanner}>
              {debuggingPlanner ? 'Debugging planner...' : 'Debug Planner'}
            </button>
          </form>
          <p className="info">Uses existing classified news only; does not fetch or classify news.</p>
          {debugPlannerError && <p className="error">{debugPlannerError}</p>}
          {debugPlannerResult && (
            <div className={debugPlannerResult.results.some((result) => result.status === 'failed') ? 'error' : 'info'}>
              <p>
                Planner debug finished for {debugPlannerResult.ticker}: {debugPlannerResult.users_processed}{' '}
                user(s) processed.
              </p>
              <ul>
                {debugPlannerResult.results.map((result) => (
                  <li key={result.user_id}>
                    {result.status === 'success' ? 'Success' : `Failed: ${result.error}`}
                  </li>
                ))}
              </ul>
            </div>
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
                  {r.items_skipped} skipped, {r.insights_generated || 0} insights generated,{' '}
                  {(r.errors || []).length} errors ({r.tickers_processed} tickers)
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
          <h2>Monitoring, efficiency &amp; cost</h2>
          <div className="inline-form">
            <label>
              Time window
              <select value={metricsWindow} onChange={(e) => setMetricsWindow(e.target.value)}>
                <option value="24h">Last 24 hours</option>
                <option value="7d">Last 7 days</option>
                <option value="30d">Last 30 days</option>
                <option value="custom">Custom range</option>
              </select>
            </label>
            {metricsWindow === 'custom' && (
              <>
                <label>
                  From
                  <input type="date" value={metricsStart} onChange={(e) => setMetricsStart(e.target.value)} />
                </label>
                <label>
                  To
                  <input type="date" value={metricsEnd} onChange={(e) => setMetricsEnd(e.target.value)} />
                </label>
              </>
            )}
            <button type="button" onClick={loadMetrics}>Refresh metrics</button>
          </div>
          {metricsError && <p className="error">{metricsError}</p>}
          {!metrics ? (
            <p>Loading...</p>
          ) : (
            <>
              <h3>Model monitoring</h3>
              {metrics.monitoring.run_count === 0 ? (
                <p>No LangSmith traces found for this window.</p>
              ) : (
                <ul className="admin-runs">
                  <li>Traced runs: {metrics.monitoring.run_count}</li>
                  <li>Errors: {metrics.monitoring.error_count}</li>
                  <li>Average latency: {metrics.monitoring.avg_latency_seconds ?? 'n/a'}s</li>
                  <li>Total tokens: {metrics.monitoring.total_tokens}</li>
                  <li>
                    Estimated cost:{' '}
                    {metrics.monitoring.estimated_cost_usd != null
                      ? `$${metrics.monitoring.estimated_cost_usd}`
                      : 'n/a'}
                  </li>
                </ul>
              )}

              <h3>Efficiency</h3>
              {metrics.efficiency.n === 0 ? (
                <p>No requests in this window yet.</p>
              ) : (
                <ul className="admin-runs">
                  <li>Requests: {metrics.efficiency.n}</li>
                  <li>
                    Steps (tool calls) - p50 {metrics.efficiency.steps.p50 ?? 'n/a'}, p95{' '}
                    {metrics.efficiency.steps.p95 ?? 'n/a'}, max {metrics.efficiency.steps.max ?? 'n/a'}
                  </li>
                  <li>
                    Tokens - p50 {metrics.efficiency.tokens.p50 ?? 'n/a'}, p95{' '}
                    {metrics.efficiency.tokens.p95 ?? 'n/a'}, max {metrics.efficiency.tokens.max ?? 'n/a'}
                  </li>
                  <li>
                    Latency (ms) - p50 {metrics.efficiency.duration_ms.p50 ?? 'n/a'}, p95{' '}
                    {metrics.efficiency.duration_ms.p95 ?? 'n/a'}, max{' '}
                    {metrics.efficiency.duration_ms.max ?? 'n/a'}
                  </li>
                  <li>Recursion-limit hit rate: {metrics.efficiency.recursion_limit_hit_rate ?? 'n/a'}</li>
                </ul>
              )}

              <h3>Alerts</h3>
              {metrics.alerts.length === 0 ? (
                <p>No alerts in this window.</p>
              ) : (
                <ul className="admin-runs">
                  {metrics.alerts.map((a) => (
                    <li key={a.id}>
                      {new Date(a.created_at).toLocaleString()} - <strong>{a.alert_type}</strong>:{' '}
                      {a.actual_value} (threshold {a.threshold})
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
          <p className="info">
            Cost, latency, errors, efficiency percentiles, and operational alerts for the selected window.
            Model quality metrics remain in the Evaluation section below.
          </p>
        </section>

        <section>
          <h2>Evaluation</h2>
          <p className="info">
            One panel per eval type this system actually scores itself against - each reuses the
            exact function the live system runs, so a score here and a production gate can never
            quietly drift apart. Every panel but Classification quality can be re-run on demand.
          </p>

          <div className="eval-panel-grid">
            <div className="eval-panel">
              <h3>Generation quality (LLM-judge)</h3>
              <p className="info">
                Judges conduct_analysis answers on a fixed question set for groundedness (is every
                claim backed by the evidence?), relevance, and advice-avoidance. Makes real, live LLM
                calls - not free, not instant, and subject to the same daily model quota as normal
                chat traffic.
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
                      grounded, {r.summary.summary.avg_completeness_pct ?? 'n/a'}% avg evidence coverage,{' '}
                      {r.summary.summary.pct_advice_avoidance_passed ?? 'n/a'}% advice-avoidance
                      pass, {r.summary.summary.pct_answer_found ?? 'n/a'}% answer found (recall) (
                      {r.summary.summary.n_judged}/{r.summary.summary.n_total} judged)
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="eval-panel">
              <h3>Insight quality (pipeline synthesis, LLM-judge)</h3>
              <p className="info">
                Same groundedness/relevance/completeness judges as generation quality, applied to
                the pipeline&apos;s own recent ticker_insights rows instead of a fixed chat question
                set - catches synthesis dropping evidence or misattributing it (e.g. peer-company
                news bleeding into another ticker&apos;s summary). Makes real, live LLM calls.
              </p>
              <button onClick={handleTriggerInsightEval} disabled={triggeringInsightEval}>
                {triggeringInsightEval ? 'Running insight eval...' : 'Run insight eval now'}
              </button>
              {insightEvalError && <p className="error">{insightEvalError}</p>}

              {insightRuns.length === 0 ? (
                <p>No insight eval runs yet.</p>
              ) : (
                <ul className="admin-runs">
                  {insightRuns.map((r) => (
                    <li key={r.id}>
                      {new Date(r.created_at).toLocaleString()} - avg relevance{' '}
                      {r.summary.summary.avg_relevance ?? 'n/a'}/5, {r.summary.summary.pct_grounded ?? 'n/a'}%
                      grounded, {r.summary.summary.avg_completeness_pct ?? 'n/a'}% avg evidence coverage (
                      {r.summary.summary.n_total} insights judged)
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="eval-panel">
              <h3>Classification quality (news &rarr; feed)</h3>
              <p className="info">
                Precision/recall/false-skip-rate + ROC-AUC of common-feed classification against a
                hand-labeled sample. The button below only RE-scores an existing labeled worksheet
                (<code>agent/eval/labeling_worksheet_filled.csv</code>) - safe to click any time
                you've changed <code>match_threshold</code> or the classifier itself and want to see
                the effect, since it needs no new labeling. A first labeled worksheet still has to
                be produced by hand once: run <code>python -m agent.eval.export_labels</code>, fill
                in the <code>correct_feed</code> column, save it at that path, then use the button.
              </p>
              <button onClick={handleTriggerClassificationEval} disabled={triggeringClassificationEval}>
                {triggeringClassificationEval ? 'Running classification eval...' : 'Run classification eval now'}
              </button>
              {classificationEvalError && <p className="error">{classificationEvalError}</p>}

              {classificationRuns.length === 0 ? (
                <p>No classification eval runs yet.</p>
              ) : (
                <>
                  <RocCurve rocAuc={classificationRuns[0].summary.roc_auc} />
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
                          {r.summary.roc_auc && (
                            <li>
                              ROC AUC {r.summary.roc_auc.auc ?? 'n/a'} - best threshold (Youden&apos;s J){' '}
                              {r.summary.roc_auc.best_threshold ?? 'n/a'}
                            </li>
                          )}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>

            <div className="eval-panel">
              <h3>Guardrail effectiveness (input &amp; output, per layer)</h3>
              <p className="info">
                True-positive rate (catches real bad questions/answers) and false-positive rate
                (wrongly blocks legitimate ones), scored independently for each guardrail&apos;s
                regex layer and LLM layer against a small hand-labeled test set - shows whether the
                cheap regex layer is pulling its weight or the LLM layer is doing all the real work.
                Grow <code>agent/eval/fixtures/input_guardrail_test_set.json</code> and{' '}
                <code>output_guardrail_test_set.json</code> over time, the same way the
                classification worksheet grows.
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
            </div>

            <div className="eval-panel">
              <h3>Research-order guardrail (chat ReAct tool-call sequencing)</h3>
              <p className="info">
                The research-order guard is deterministic (must check internal cached news before
                external/peer/report sources), so this is a labeled regression check, not judgment
                against ambiguous input - it replays real call sequences through the live guard and
                makes no LLM calls. Grow <code>agent/eval/fixtures/research_order_test_set.json</code>{' '}
                if the guard's rules change.
              </p>
              <button onClick={handleTriggerResearchOrderEval} disabled={triggeringResearchOrderEval}>
                {triggeringResearchOrderEval ? 'Running research-order eval...' : 'Run research-order eval now'}
              </button>
              {researchOrderEvalError && <p className="error">{researchOrderEvalError}</p>}

              {researchOrderRuns.length === 0 ? (
                <p>No research-order eval runs yet.</p>
              ) : (
                <ul className="admin-runs">
                  {researchOrderRuns.map((r) => (
                    <li key={r.id}>
                      {new Date(r.created_at).toLocaleString()} - TPR {r.summary.summary.true_positive_rate ?? 'n/a'},
                      FPR {r.summary.summary.false_positive_rate ?? 'n/a'} (n={r.summary.summary.n})
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="eval-panel">
              <h3>Continuous monitoring (random live-traffic sample)</h3>
              <p className="info">
                Judges a random sample of real recent conduct_analysis requests (not a fixed fixture
                set) for groundedness, relevance, and answer-discovery - a small fixed sample size
                (10/day by default) keeps judging cost predictable regardless of how much real
                traffic there is.
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
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
