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

// Streams agent/eval/fixtures/labeling_worksheet.csv from the server through the
// authenticated fetch helper (a plain <a href> can't carry the Bearer token) and hands
// the browser a Blob to save - the standard SPA pattern for an auth-gated download.
async function downloadClassificationLabelsFile() {
  const res = await authedFetch('/api/admin/eval/classification/labels-file');
  if (!res.ok) {
    alert('Could not download the labeled worksheet - it may not exist on the server yet.');
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'labeling_worksheet_filled.csv';
  a.click();
  URL.revokeObjectURL(url);
}

// Three columns for one classification eval run: the labeled CSV it was scored against,
// every observed similarity value swept as a threshold (see
// agent/eval/runners/run_classification_eval.py::compute_pr_auc) with its Recall/Precision, and a
// plain-language explanation of the two "best threshold" picks that curve implies.
// Reuses the same .quality-sample-columns/-column layout QualitySampleCard uses below,
// rather than a chart - recall/precision are exact numbers; a 180px inline SVG plot
// couldn't show them precisely enough to actually pick a threshold from.
//
// Precision-recall, not ROC/FPR: real news is heavily skewed toward "belongs to none of
// the 3 templates" (see the labeled worksheet's own class balance), which dilutes FPR's
// denominator and makes an ROC curve look better than the classifier actually performs.
// Precision and recall never involve a true-negative count, so they stay honest about
// the tradeoff that matters on an imbalanced feed - see compute_pr_auc's docstring.
function ClassificationThresholdPanel({ summary }) {
  const prAuc = summary.pr_auc;
  const points = (prAuc?.pr_points || []).filter((p) => p.threshold != null);
  const best = prAuc?.best_threshold_metrics;
  const bestRw = prAuc?.best_threshold_recall_weighted_metrics;

  return (
    <div className="quality-sample-columns">
      <div className="quality-sample-column">
        <h4>Labeled worksheet</h4>
        <p>
          <button type="button" className="link-button" onClick={downloadClassificationLabelsFile}>
            {summary.labels_file || 'labeling_worksheet_filled.csv'}
          </button>
        </p>
        <p>Hand-labeled CSV this run was scored against (see export_labels.py).</p>
      </div>

      <div className="quality-sample-column">
        <h4>Recall / Precision by threshold</h4>
        {points.length === 0 ? (
          <p>No PR data on this run - re-run with --pr-auc.</p>
        ) : (
          <table className="quality-evidence-list" style={{ width: '100%' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left' }}>Threshold</th>
                <th style={{ textAlign: 'left' }}>Recall</th>
                <th style={{ textAlign: 'left' }}>Precision</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p, i) => (
                <tr key={i} className={p.threshold === prAuc.best_threshold ? 'quality-score good' : undefined}>
                  <td>{p.threshold.toFixed(4)}</td>
                  <td>{p.recall.toFixed(4)}</td>
                  <td>{p.precision == null ? '—' : p.precision.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="quality-sample-column">
        <h4>Best threshold</h4>
        {prAuc ? (
          <>
            <p>PR AUC (Average Precision) {prAuc.auc ?? 'n/a'}</p>
            {prAuc.best_threshold != null && (
              <p>
                Best F1: <strong>{prAuc.best_threshold}</strong> (recall={best?.recall ?? 'n/a'}, precision=
                {best?.precision ?? 'n/a'}) - treats a missed match and a
                wrongly-accepted one as equally costly.
              </p>
            )}
            {prAuc.best_threshold_recall_weighted != null && (
              <p>
                Recall-weighted (F{prAuc.beta ?? '?'}): <strong>{prAuc.best_threshold_recall_weighted}</strong>{' '}
                (recall={bestRw?.recall ?? 'n/a'}, precision={bestRw?.precision ?? 'n/a'}) -
                weights recall higher, since a missed match silently drops real evidence from a feed while a
                wrongly-accepted one is just noise a user skims past.
              </p>
            )}
            <p className="info">
              Recall here is narrower than the summary line above it - it only covers rows where the
              classifier&rsquo;s own top-1 candidate already matched the correct feed, so a threshold change can
              raise it to 1.0 by accepting those. Rows where the embedding search picked the wrong feed entirely
              aren&rsquo;t counted here at all - no threshold can fix a wrong top-1 guess, only better matching
              can - which is why the summary line&rsquo;s recall can still sit well below this panel&rsquo;s.
            </p>
          </>
        ) : (
          <p>No PR data on this run.</p>
        )}
      </div>
    </div>
  );
}

const QUALITY_SURFACE_LABELS = {
  // custom_feed/common_feed are retired (sample_custom_feed_quality/
  // sample_common_feed_quality were replaced by sample_feed_combine_quality - see
  // monitoring/quality_sampling.py) but kept here so historical quality_samples rows
  // from before the change still render a real label instead of the raw surface_type.
  custom_feed: 'Custom feed (retired)',
  common_feed: 'Common feed (retired)',
  feed_combine: 'Feed summary',
  insight: 'Insight',
  chat_answer: 'Chat answer',
};

// Column 1/2 headers and content differ by surface_type - what's being verified is a
// different shape each time (a chat Q&A vs. a one-line feed summary vs. a synthesized
// "god summary" over several feeds), so the reviewer needs different context to judge
// each one. Column 3 (scores/explanation) is always the same shape.
function QualitySampleEvidence({ evidence }) {
  if (!evidence || evidence.length === 0) return <p className="quality-empty">No evidence recorded.</p>;
  return (
    <ul className="quality-evidence-list">
      {evidence.map((e, i) => (
        <li key={i}>
          <strong>{e.source}</strong>
          {e.url ? (
            <>
              :{' '}
              <a href={e.url} target="_blank" rel="noreferrer">
                {e.content}
              </a>
            </>
          ) : (
            <>: {e.content}</>
          )}
        </li>
      ))}
    </ul>
  );
}

// Claims recorded before the structured {statement, issue_type, explanation} shape
// shipped are plain strings - render those with a neutral fallback instead of crashing.
function QualityClaim({ claim }) {
  if (typeof claim === 'string') {
    return <li className="quality-claim">{claim}</li>;
  }
  const isContradicting = claim.issue_type === 'contradicting';
  return (
    <li className="quality-claim">
      <span className={`quality-claim-badge ${isContradicting ? 'contradicting' : 'unsupported'}`}>
        {isContradicting ? 'Contradicting' : 'Unsupported'}
      </span>
      <span className="quality-claim-statement">{claim.statement}</span>
      <span className="quality-claim-explanation"> - {claim.explanation}</span>
    </li>
  );
}

function QualitySampleCard({ sample: s, onReview }) {
  const isFeed = s.surface_type === 'custom_feed' || s.surface_type === 'common_feed' || s.surface_type === 'feed_combine';
  const isInsight = s.surface_type === 'insight';
  const isChat = s.surface_type === 'chat_answer';

  const col1Title = isChat ? 'Question' : isFeed ? 'Feed' : 'Feed summaries';
  const col2Title = isChat ? 'Answer & references' : isFeed ? 'Feed summary & source news' : 'Insight ("god summary")';

  return (
    <div className={`quality-sample-card${s.flagged ? ' flagged' : ''}`}>
      <div className="quality-sample-header">
        <span className="quality-badge">{QUALITY_SURFACE_LABELS[s.surface_type] || s.surface_type}</span>
        <strong>{s.ticker || 'n/a'}</strong>
        <span className="info">{new Date(s.created_at).toLocaleString()}</span>
        {s.flagged && <span className="quality-badge flagged">FLAGGED</span>}
        {s.reviewed_at && (
          <span className="info">reviewed {new Date(s.reviewed_at).toLocaleString()}</span>
        )}
      </div>

      <div className="quality-sample-columns">
        <div className="quality-sample-column">
          <h4>{col1Title}</h4>
          {isChat && <p>{s.question}</p>}
          {isFeed && <p>{s.context || s.question}</p>}
          {isInsight && <QualitySampleEvidence evidence={s.evidence} />}
        </div>

        <div className="quality-sample-column">
          <h4>{col2Title}</h4>
          <p>{s.text}</p>
          {(isChat || isFeed) && (
            <>
              <h4>References</h4>
              <QualitySampleEvidence evidence={s.evidence} />
            </>
          )}
        </div>

        <div className="quality-sample-column">
          <h4>Scores &amp; explanation</h4>
          <div className="quality-score-row">
            <p className={`quality-score ${s.groundedness_pct === 100 || (s.groundedness_pct == null && s.grounded) ? 'good' : 'bad'}`}>
              Groundedness{' '}
              {s.groundedness_pct != null ? `${s.groundedness_pct}%` : s.grounded ? '100%' : 'n/a'}
            </p>
            <p className={`quality-score ${s.completeness_pct != null && s.completeness_pct >= 80 ? 'good' : 'bad'}`}>
              Completeness {s.completeness_pct != null ? `${s.completeness_pct}%` : 'n/a'}
            </p>
          </div>

          {s.unsupported_claims && s.unsupported_claims.length > 0 && (
            <>
              <h4>Groundedness issues</h4>
              <ul className="quality-claims-list">
                {s.unsupported_claims.map((c, i) => (
                  <QualityClaim key={i} claim={c} />
                ))}
              </ul>
            </>
          )}
          {s.omitted_points && s.omitted_points.length > 0 && (
            <>
              <h4>Omitted from answer</h4>
              <ul className="quality-omitted-list">
                {s.omitted_points.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </>
          )}
          {s.flagged && !s.reviewed_at && (
            <button type="button" onClick={() => onReview(s)}>
              Mark reviewed
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const GUARDRAIL_TYPE_LABELS = {
  input: 'Input guardrail',
  output: 'Output guardrail',
};

// 3 columns: 1) what was judged (user question or agent output), 2) the two LIVE
// production layers' own verdicts on this request (regex + LLM), 3) the independent
// evaluation-tier judge's verdict + reasoning - see monitoring/guardrail_sampling.py
// for why column 2 and column 3 use different model tiers on the input side.
function GuardrailSampleCard({ sample: s, onReview }) {
  const isInput = s.guardrail_type === 'input';

  return (
    <div className={`quality-sample-card${s.flagged ? ' flagged' : ''}`}>
      <div className="quality-sample-header">
        <span className="quality-badge">{GUARDRAIL_TYPE_LABELS[s.guardrail_type] || s.guardrail_type}</span>
        <strong>{s.ticker || 'n/a'}</strong>
        <span className="info">{new Date(s.created_at).toLocaleString()}</span>
        {s.flagged && <span className="quality-badge flagged">FLAGGED</span>}
        {s.reviewed_at && (
          <span className="info">reviewed {new Date(s.reviewed_at).toLocaleString()}</span>
        )}
      </div>

      <div className="quality-sample-columns">
        <div className="quality-sample-column">
          <h4>{isInput ? 'User input' : "Agent's output"}</h4>
          <p>{s.text}</p>
        </div>

        <div className="quality-sample-column">
          <h4>Live guardrail verdicts</h4>
          <p className={`quality-score ${s.regex_flagged ? 'bad' : 'good'}`}>
            Regex layer: {s.regex_flagged ? 'Flagged' : 'Clean'}
          </p>
          <p className={`quality-score ${s.llm_flagged == null ? '' : s.llm_flagged ? 'bad' : 'good'}`}>
            LLM layer: {s.llm_flagged == null ? 'Not reached' : s.llm_flagged ? 'Flagged' : 'Clean'}
          </p>
        </div>

        <div className="quality-sample-column">
          <h4>Evaluation &amp; explanation</h4>
          <p className={`quality-score ${s.eval_flagged ? 'bad' : 'good'}`}>
            Evaluation LLM: {s.eval_flagged ? 'Flagged' : 'Clean'}
          </p>
          <p>{s.eval_reasoning}</p>
          {s.flagged && !s.reviewed_at && (
            <button type="button" onClick={() => onReview(s)}>
              Mark reviewed
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const CLASSIFICATION_TYPE_LABELS = {
  custom_feed: 'Custom feed classification',
  common_feed: 'Common feed classification',
};

// 3 columns: 1) the article that was classified, 2) which feed it was matched to and
// why that feed exists, 3) whether an independent judge thinks the match is actually
// correct - see monitoring/classification_sampling.py for why this exists (the live
// classifier only checks embedding similarity, with no semantic verification).
function ClassificationSampleCard({ sample: s, onReview }) {
  return (
    <div className={`quality-sample-card${s.flagged ? ' flagged' : ''}`}>
      <div className="quality-sample-header">
        <span className="quality-badge">{CLASSIFICATION_TYPE_LABELS[s.classification_type] || s.classification_type}</span>
        <strong>{s.ticker || 'n/a'}</strong>
        <span className="info">{new Date(s.created_at).toLocaleString()}</span>
        {s.flagged && <span className="quality-badge flagged">FLAGGED</span>}
        {s.reviewed_at && (
          <span className="info">reviewed {new Date(s.reviewed_at).toLocaleString()}</span>
        )}
      </div>

      <div className="quality-sample-columns">
        <div className="quality-sample-column">
          <h4>Article</h4>
          <p>{s.article_title}</p>
        </div>

        <div className="quality-sample-column">
          <h4>Assigned feed</h4>
          <p>
            <strong>{s.feed_name}</strong>
          </p>
          <p>{s.feed_description}</p>
        </div>

        <div className="quality-sample-column">
          <h4>Evaluation &amp; explanation</h4>
          <p className={`quality-score ${s.eval_correct ? 'good' : 'bad'}`}>
            Classification: {s.eval_correct ? 'Correct match' : 'Likely misclassified'}
          </p>
          <p>{s.eval_reasoning}</p>
          {s.flagged && !s.reviewed_at && (
            <button type="button" onClick={() => onReview(s)}>
              Mark reviewed
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Evaluation section cards - fixed test-set items, no filters (unlike the Monitoring
// panel above), so each just renders the LATEST run's per-item results as 3-column
// cards: what was judged, the relevant context, then scores/explanation - same
// skeleton as the Monitoring cards, reusing QualitySampleEvidence/QualityClaim so the
// claim-badge/highlight styling can't drift between the two sections.

function ChatAnswerEvalItemCard({ item }) {
  // item.groundedness/completeness can be null on a run persisted before this eval was
  // rewritten to call synthesize_insight() directly (see run_chat_answer_eval.py) - the
  // old shape left them null for any question the live router declined instead of
  // routing to conduct_analysis. Old eval_runs rows stay in history (that's what the
  // judge-drift check compares against), so this card has to tolerate that shape too,
  // not just the current one - re-run the eval to get a fresh, fully-scored row.
  const judged = item.groundedness != null;
  return (
    <div className={`quality-sample-card${judged && !item.groundedness.grounded ? ' flagged' : ''}`}>
      <div className="quality-sample-header">
        <strong>{item.ticker}</strong>
      </div>
      <div className="quality-sample-columns">
        <div className="quality-sample-column">
          <h4>Question</h4>
          <p>{item.question}</p>
          <h4>Sample facts given</h4>
          <QualitySampleEvidence evidence={item.evidence} />
        </div>
        <div className="quality-sample-column">
          <h4>Answer</h4>
          <p>{item.answer}</p>
        </div>
        <div className="quality-sample-column">
          <h4>Scores &amp; explanation</h4>
          {!judged ? (
            <p>Not scored - this run predates the current chat-answer eval; re-run to see scores.</p>
          ) : (
          <>
          <div className="quality-score-row">
            <p className={`quality-score ${(item.groundedness.groundedness_pct ?? (item.groundedness.grounded ? 100 : 0)) === 100 ? 'good' : 'bad'}`}>
              Groundedness {item.groundedness.groundedness_pct != null ? `${item.groundedness.groundedness_pct}%` : (item.groundedness.grounded ? '100%' : 'n/a')}
            </p>
            <p className={`quality-score ${item.completeness && item.completeness.coverage_pct >= 80 ? 'good' : 'bad'}`}>
              Completeness {item.completeness ? `${item.completeness.coverage_pct}%` : 'n/a'}
            </p>
          </div>
          {item.groundedness.unsupported_claims && item.groundedness.unsupported_claims.length > 0 && (
            <>
              <h4>Groundedness issues</h4>
              <ul className="quality-claims-list">
                {item.groundedness.unsupported_claims.map((c, i) => (
                  <QualityClaim key={i} claim={c} />
                ))}
              </ul>
            </>
          )}
          {item.completeness && item.completeness.omitted_points.length > 0 && (
            <>
              <h4>Omitted from answer</h4>
              <ul className="quality-omitted-list">
                {item.completeness.omitted_points.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </>
          )}
          </>
          )}
        </div>
      </div>
    </div>
  );
}

function InsightEvalItemCard({ item }) {
  return (
    <div className={`quality-sample-card${!item.groundedness.grounded ? ' flagged' : ''}`}>
      <div className="quality-sample-header">
        <strong>{item.ticker}</strong>
      </div>
      <div className="quality-sample-columns">
        <div className="quality-sample-column">
          <h4>Feed summaries</h4>
          <QualitySampleEvidence evidence={item.evidence} />
        </div>
        <div className="quality-sample-column">
          <h4>Insight (&quot;god summary&quot;)</h4>
          <p>{item.insight_text}</p>
        </div>
        <div className="quality-sample-column">
          <h4>Scores &amp; explanation</h4>
          <div className="quality-score-row">
            <p className={`quality-score ${(item.groundedness.groundedness_pct ?? (item.groundedness.grounded ? 100 : 0)) === 100 ? 'good' : 'bad'}`}>
              Groundedness {item.groundedness.groundedness_pct}%
            </p>
            <p className={`quality-score ${item.completeness && item.completeness.coverage_pct >= 80 ? 'good' : 'bad'}`}>
              Completeness {item.completeness ? `${item.completeness.coverage_pct}%` : 'n/a'}
            </p>
          </div>
          {item.groundedness.unsupported_claims && item.groundedness.unsupported_claims.length > 0 && (
            <>
              <h4>Groundedness issues</h4>
              <ul className="quality-claims-list">
                {item.groundedness.unsupported_claims.map((c, i) => (
                  <QualityClaim key={i} claim={c} />
                ))}
              </ul>
            </>
          )}
          {item.completeness && item.completeness.omitted_points.length > 0 && (
            <>
              <h4>Omitted from answer</h4>
              <ul className="quality-omitted-list">
                {item.completeness.omitted_points.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function FeedSummaryEvalItemCard({ item }) {
  return (
    <div className={`quality-sample-card${!item.groundedness.grounded ? ' flagged' : ''}`}>
      <div className="quality-sample-header">
        <span className="quality-badge">{item.feed_name}</span>
        <strong>{item.ticker}</strong>
        <span className="info">{(item.news_titles || []).length} news item(s)</span>
      </div>
      <div className="quality-sample-columns">
        <div className="quality-sample-column">
          <h4>News &amp; feed description</h4>
          <ul className="quality-evidence-list">
            {(item.news_titles || []).map((title, i) => (
              <li key={i}>{title}</li>
            ))}
          </ul>
          <p>{item.feed_description}</p>
        </div>
        <div className="quality-sample-column">
          <h4>Generated summary</h4>
          <p>{item.summary}</p>
          <p className={`quality-score ${item.sufficient ? 'good' : 'bad'}`}>
            {item.sufficient ? 'Sufficient' : 'Insufficient'} evidence
          </p>
        </div>
        <div className="quality-sample-column">
          <h4>Scores &amp; explanation</h4>
          <div className="quality-score-row">
            <p className={`quality-score ${item.groundedness.groundedness_pct === 100 ? 'good' : 'bad'}`}>
              Groundedness {item.groundedness.groundedness_pct}%
            </p>
            <p className={`quality-score ${item.completeness.coverage_pct >= 80 ? 'good' : 'bad'}`}>
              Completeness {item.completeness.coverage_pct}%
            </p>
          </div>
          {item.groundedness.unsupported_claims && item.groundedness.unsupported_claims.length > 0 && (
            <>
              <h4>Groundedness issues</h4>
              <ul className="quality-claims-list">
                {item.groundedness.unsupported_claims.map((c, i) => (
                  <QualityClaim key={i} claim={c} />
                ))}
              </ul>
            </>
          )}
          {item.completeness.omitted_points && item.completeness.omitted_points.length > 0 && (
            <>
              <h4>Omitted from summary</h4>
              <ul className="quality-omitted-list">
                {item.completeness.omitted_points.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const CLASSIFICATION_OUTCOME_LABELS = {
  correct: 'Correct',
  wrong_feed: 'Wrong feed',
  false_skip: 'False skip (missed)',
};

function ClassificationEvalItemCard({ item }) {
  const isWrong = item.outcome !== 'correct';
  return (
    <div className={`quality-sample-card${isWrong ? ' flagged' : ''}`}>
      <div className="quality-sample-header">
        <span className={`quality-badge${isWrong ? ' flagged' : ''}`}>
          {CLASSIFICATION_OUTCOME_LABELS[item.outcome] || item.outcome}
        </span>
      </div>
      <div className="quality-sample-columns">
        <div className="quality-sample-column">
          <h4>Article</h4>
          <p>{item.title}</p>
        </div>
        <div className="quality-sample-column">
          <h4>Predicted vs. correct feed</h4>
          <p>
            <strong>Predicted:</strong> {item.predicted_feed}
          </p>
          <p>
            <strong>Correct:</strong> {item.correct_feed}
          </p>
        </div>
        <div className="quality-sample-column">
          <h4>Result</h4>
          <p className={`quality-score ${isWrong ? 'bad' : 'good'}`}>
            {CLASSIFICATION_OUTCOME_LABELS[item.outcome] || item.outcome}
          </p>
          <p>Similarity: {item.similarity != null ? item.similarity.toFixed(3) : 'n/a'}</p>
        </div>
      </div>
    </div>
  );
}

function GuardrailEvalItemCard({ text, isBad, regexPredicted, llmPredicted }) {
  const anyWrong = regexPredicted !== isBad || llmPredicted !== isBad;
  return (
    <div className={`quality-sample-card${anyWrong ? ' flagged' : ''}`}>
      <div className="quality-sample-header">
        <span className={`quality-badge${isBad ? ' flagged' : ''}`}>{isBad ? 'Should flag' : 'Should pass'}</span>
      </div>
      <div className="quality-sample-columns">
        <div className="quality-sample-column">
          <h4>Text</h4>
          <p>{text}</p>
        </div>
        <div className="quality-sample-column">
          <h4>Live layer predictions</h4>
          <p className={`quality-score ${regexPredicted === isBad ? 'good' : 'bad'}`}>
            Regex: {regexPredicted ? 'Flagged' : 'Clean'}
          </p>
          <p className={`quality-score ${llmPredicted === isBad ? 'good' : 'bad'}`}>
            LLM: {llmPredicted ? 'Flagged' : 'Clean'}
          </p>
        </div>
        <div className="quality-sample-column">
          <h4>Label vs. prediction</h4>
          <p>Actual label: {isBad ? 'Bad (should be flagged)' : 'Clean (should pass)'}</p>
          <p className={`quality-score ${!anyWrong ? 'good' : 'bad'}`}>
            {anyWrong ? 'At least one layer got this wrong' : 'Both layers correct'}
          </p>
        </div>
      </div>
    </div>
  );
}

// Research-order guardrail eval still exists and is triggerable via CLI/API
// (agent/eval/runners/run_research_order_eval.py, POST /api/admin/eval/research-order/trigger) -
// just deprioritized out of this dropdown, not deleted (see docs/pipeline_guardrails.csv).

function EvidenceSelectionEvalItemCard({ item }) {
  const allCorrect = item.per_feed.every((f) => f.reports_correct && f.peer_news_correct);
  return (
    <div className={`quality-sample-card${!allCorrect ? ' flagged' : ''}`}>
      <div className="quality-sample-header">
        <strong>{item.ticker}</strong>
      </div>
      <table className="quality-evidence-list" style={{ width: '100%' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left' }}>Feed</th>
            <th style={{ textAlign: 'left' }}>needs_reports (expected / actual)</th>
            <th style={{ textAlign: 'left' }}>needs_peer_news (expected / actual)</th>
          </tr>
        </thead>
        <tbody>
          {item.per_feed.map((f, i) => (
            <tr key={i}>
              <td>{f.feed_name}</td>
              <td className={`quality-score ${f.reports_correct ? 'good' : 'bad'}`}>
                {String(f.expected.needs_reports)} / {String(f.predicted.needs_reports)}
              </td>
              <td className={`quality-score ${f.peer_news_correct ? 'good' : 'bad'}`}>
                {String(f.expected.needs_peer_news)} / {String(f.predicted.needs_peer_news)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Judge-drift reports aren't a labeled/predicted fixture the way other eval types are -
// they diff two ALREADY-SCORED runs against each other (see run_judge_drift_check.py), so
// this renders that diff shape directly rather than reusing the generic ItemCard
// pattern above.
function JudgeDriftItemCard({ item }) {
  const g = item.deltas.groundedness_pct;
  const c = item.deltas.completeness_pct;
  return (
    <div className={`quality-sample-card${item.flagged ? ' flagged' : ''}`}>
      <div className="quality-sample-header">
        <strong>{item.id}</strong>
        {item.flagged && <span className="quality-badge flagged">Flagged for review</span>}
      </div>
      <div className="quality-score-row">
        <p className={`quality-score ${g.delta == null || Math.abs(g.delta) < 10 ? 'good' : 'bad'}`}>
          Groundedness {g.old} → {g.new} (Δ{g.delta})
        </p>
        <p className={`quality-score ${c.delta == null || Math.abs(c.delta) < 10 ? 'good' : 'bad'}`}>
          Completeness {c.old} → {c.new} (Δ{c.delta})
        </p>
      </div>
    </div>
  );
}

function JudgeDriftReport({ report }) {
  if (!report) return <p>No judge-drift check run yet for this eval type.</p>;
  if (report.status === 'no_baseline') {
    return <p className="info">{report.message}</p>;
  }
  return (
    <>
      {report.fixture_changed && (
        <p className="info" style={{ color: '#b3261e', fontWeight: 600 }}>
          Fixture changed between these two runs ({report.old_fixture_version} → {report.new_fixture_version}) -
          deltas below may reflect an edited test case, not judge/prompt drift.
        </p>
      )}
      <p className="info">
        Comparing run {new Date(report.old_run_created_at).toLocaleString()} →{' '}
        {new Date(report.new_run_created_at).toLocaleString()}: {report.n_matched} matched items,{' '}
        {report.n_flagged} flagged (≥{report.threshold} pt delta), rate {report.flagged_rate ?? 'n/a'}.
        {report.new_items_no_baseline.length > 0 &&
          ` ${report.new_items_no_baseline.length} item(s) have no prior baseline yet.`}
      </p>
      <div className="quality-sample-list">
        {report.matched.map((item, i) => (
          <JudgeDriftItemCard key={i} item={item} />
        ))}
      </div>
    </>
  );
}

export default function Admin() {
  const { user, loading } = useRequireAuth();
  const [forbidden, setForbidden] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [runs, setRuns] = useState([]);
  const [runsStartDate, setRunsStartDate] = useState('');
  const [runsEndDate, setRunsEndDate] = useState('');
  const [runsOffset, setRunsOffset] = useState(0);
  const RUNS_PAGE_SIZE = 10;
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

  const [chatAnswerRuns, setChatAnswerRuns] = useState([]);
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

  const [evidenceSelectionRuns, setEvidenceSelectionRuns] = useState([]);
  const [triggeringEvidenceSelectionEval, setTriggeringEvidenceSelectionEval] = useState(false);
  const [evidenceSelectionEvalError, setEvidenceSelectionEvalError] = useState('');

  // Both judge-drift variants share one eval_type column value ('judge_drift') in the
  // DB - the payload's own summary.eval_type field (either 'feed_summary' or
  // 'insight_quality') is what tells them apart, so one fetch/state covers both and the
  // two dropdown entries just filter this same array.
  const [judgeDriftRuns, setJudgeDriftRuns] = useState([]);
  const [triggeringJudgeDrift, setTriggeringJudgeDrift] = useState(false);
  const [judgeDriftEvalError, setJudgeDriftEvalError] = useState('');

  const [feedSummaryRuns, setFeedSummaryRuns] = useState([]);
  const [triggeringFeedSummaryEval, setTriggeringFeedSummaryEval] = useState(false);
  const [feedSummaryEvalError, setFeedSummaryEvalError] = useState('');

  // Unified panel like Monitoring above, but simpler: all 6 eval types' runs are
  // already fetched together (loadEvalRuns), so this dropdown only picks which one's
  // latest-run cards to display - no separate fetch/endpoint per option the way
  // Monitoring's dropdown needs, and the trigger button re-runs only the selected type
  // (not all 6 together - unlike Monitoring's capped/cheap samplers, these are full,
  // uncapped fixture runs, so batching them into one click would be both expensive and,
  // for Classification, likely to fail if no labeled worksheet exists yet).
  const [evalFilterType, setEvalFilterType] = useState('chat_answer');

  // Unified panel: one filter bar/list over BOTH quality_samples (business-metric
  // surfaces) and guardrail_samples (input/output guardrails) - `monitorFilterType`
  // picks which bucket is displayed ('' or a surface_type = quality_samples;
  // 'guardrail_input'/'guardrail_output'/'guardrail_all' = guardrail_samples), so only
  // one endpoint is ever fetched per selection. Each fetched row is tagged with
  // `_kind` (see loadMonitorSamples) so the list knows which card component to render.
  const [monitorSamples, setMonitorSamples] = useState([]);
  const [monitorFilterType, setMonitorFilterType] = useState('');
  // Independent from metricsWindow (Model monitoring/Efficiency/Alerts) below - sampling
  // reads each surface's own source table directly, not the LangSmith/request_trace
  // aggregates metricsWindow drives, and demo-scale data is often sparser than a fixed
  // 24h window can find, hence a separate, longer default here.
  const [monitorSampleWindow, setMonitorSampleWindow] = useState('7d');
  const [monitorFlaggedOnly, setMonitorFlaggedOnly] = useState(true);
  const [monitorTickerFilter, setMonitorTickerFilter] = useState('');
  const [monitorStartDate, setMonitorStartDate] = useState('');
  const [monitorEndDate, setMonitorEndDate] = useState('');
  const [monitorReviewedFilter, setMonitorReviewedFilter] = useState('');
  const [triggeringSampling, setTriggeringSampling] = useState(false);
  const [samplingError, setSamplingError] = useState('');


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

  async function loadRuns(offset = runsOffset) {
    const params = new URLSearchParams();
    params.set('limit', RUNS_PAGE_SIZE);
    params.set('offset', offset);
    if (runsStartDate) params.set('start', new Date(`${runsStartDate}T00:00:00`).toISOString());
    if (runsEndDate) params.set('end', new Date(`${runsEndDate}T23:59:59.999`).toISOString());
    const data = await fetchJsonOrForbidden(`/api/admin/pipeline/runs?${params.toString()}`);
    if (data) setRuns(data);
  }

  function handleRunsFilterChange() {
    setRunsOffset(0);
    loadRuns(0);
  }

  function handleRunsPrevPage() {
    const offset = Math.max(0, runsOffset - RUNS_PAGE_SIZE);
    setRunsOffset(offset);
    loadRuns(offset);
  }

  function handleRunsNextPage() {
    const offset = runsOffset + RUNS_PAGE_SIZE;
    setRunsOffset(offset);
    loadRuns(offset);
  }

  async function loadEvalRuns() {
    const [chatAnswerData, classData, insightData, feedSummaryData, guardrailData, evidenceSelectionData, judgeDriftData] =
      await Promise.all([
        fetchJsonOrForbidden('/api/admin/eval/runs?eval_type=chat_answer'),
        fetchJsonOrForbidden('/api/admin/eval/runs?eval_type=classification'),
        fetchJsonOrForbidden('/api/admin/eval/runs?eval_type=insight_quality'),
        fetchJsonOrForbidden('/api/admin/eval/runs?eval_type=feed_summary'),
        fetchJsonOrForbidden('/api/admin/eval/runs?eval_type=guardrails'),
        fetchJsonOrForbidden('/api/admin/eval/runs?eval_type=evidence_selection'),
        fetchJsonOrForbidden('/api/admin/eval/runs?eval_type=judge_drift'),
      ]);
    if (chatAnswerData) setChatAnswerRuns(chatAnswerData);
    if (classData) setClassificationRuns(classData);
    if (insightData) setInsightRuns(insightData);
    if (feedSummaryData) setFeedSummaryRuns(feedSummaryData);
    if (guardrailData) setGuardrailRuns(guardrailData);
    if (evidenceSelectionData) setEvidenceSelectionRuns(evidenceSelectionData);
    if (judgeDriftData) setJudgeDriftRuns(judgeDriftData);
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

  function _isGuardrailFilter(filterType) {
    return filterType.startsWith('guardrail');
  }

  function _isClassificationFilter(filterType) {
    return filterType.startsWith('classification');
  }

  async function loadMonitorSamples() {
    const params = new URLSearchParams();
    if (monitorTickerFilter.trim()) params.set('ticker', monitorTickerFilter.trim().toUpperCase());
    if (monitorStartDate) params.set('start', new Date(`${monitorStartDate}T00:00:00`).toISOString());
    if (monitorEndDate) params.set('end', new Date(`${monitorEndDate}T23:59:59.999`).toISOString());
    if (monitorReviewedFilter) params.set('reviewed', monitorReviewedFilter === 'reviewed' ? 'true' : 'false');
    if (monitorFlaggedOnly) params.set('flagged_only', 'true');

    if (_isGuardrailFilter(monitorFilterType)) {
      if (monitorFilterType === 'guardrail_input') params.set('guardrail_type', 'input');
      if (monitorFilterType === 'guardrail_output') params.set('guardrail_type', 'output');
      const data = await fetchJsonOrForbidden(`/api/admin/monitoring/guardrail-samples?${params.toString()}`);
      if (data) setMonitorSamples(data.map((s) => ({ ...s, _kind: 'guardrail' })));
    } else if (_isClassificationFilter(monitorFilterType)) {
      if (monitorFilterType === 'classification_custom_feed') params.set('classification_type', 'custom_feed');
      if (monitorFilterType === 'classification_common_feed') params.set('classification_type', 'common_feed');
      const data = await fetchJsonOrForbidden(`/api/admin/monitoring/classification-samples?${params.toString()}`);
      if (data) setMonitorSamples(data.map((s) => ({ ...s, _kind: 'classification' })));
    } else {
      if (monitorFilterType) params.set('surface_type', monitorFilterType);
      const data = await fetchJsonOrForbidden(`/api/admin/monitoring/quality-samples?${params.toString()}`);
      if (data) setMonitorSamples(data.map((s) => ({ ...s, _kind: 'quality' })));
    }
  }

  function monitorSampleWindowHours() {
    return monitorSampleWindow === '24h' ? 24 : monitorSampleWindow === '7d' ? 168 : 720;
  }

  async function handleTriggerSampling() {
    setTriggeringSampling(true);
    setSamplingError('');
    const hours = monitorSampleWindowHours();
    const [qRes, gRes, cRes] = await Promise.all([
      authedFetch(`/api/admin/monitoring/quality-sampling/trigger?hours=${hours}`, { method: 'POST' }),
      authedFetch(`/api/admin/monitoring/guardrail-sampling/trigger?hours=${hours}`, { method: 'POST' }),
      authedFetch(`/api/admin/monitoring/classification-sampling/trigger?hours=${hours}`, { method: 'POST' }),
    ]);
    setTriggeringSampling(false);

    if (qRes.status === 403 || gRes.status === 403 || cRes.status === 403) {
      setForbidden(true);
      return;
    }
    if (!qRes.ok || !gRes.ok || !cRes.ok) {
      const failed = [qRes, gRes, cRes].find((r) => !r.ok);
      const body = await failed.json().catch(() => ({}));
      setSamplingError(body.detail || 'Failed to run sampling.');
      return;
    }
    loadMonitorSamples();
  }

  async function handleReviewSample(sample) {
    const path =
      sample._kind === 'guardrail'
        ? `/api/admin/monitoring/guardrail-samples/${sample.id}/review`
        : sample._kind === 'classification'
        ? `/api/admin/monitoring/classification-samples/${sample.id}/review`
        : `/api/admin/monitoring/quality-samples/${sample.id}/review`;
    const res = await authedFetch(path, { method: 'POST' });
    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (res.ok) loadMonitorSamples();
  }

  const monitorActiveFilterCount = [
    monitorFilterType,
    monitorTickerFilter.trim(),
    monitorStartDate,
    monitorEndDate,
    monitorReviewedFilter,
  ].filter(Boolean).length;

  async function handleClearMonitorFilters() {
    setMonitorFilterType('');
    setMonitorTickerFilter('');
    setMonitorStartDate('');
    setMonitorEndDate('');
    setMonitorReviewedFilter('');
    setMonitorFlaggedOnly(true);
    // Fetches with the known-cleared params directly rather than relying on the
    // useEffect below - React batches these setState calls, so reading monitorXxx
    // state right after calling their setters here would still see the pre-clear
    // values, and the effect only re-fires when one of ITS watched deps actually
    // changes (e.g. clearing just the ticker/date fields wouldn't trigger it).
    const data = await fetchJsonOrForbidden('/api/admin/monitoring/quality-samples?flagged_only=true');
    if (data) setMonitorSamples(data.map((s) => ({ ...s, _kind: 'quality' })));
  }

  async function handleTriggerChatAnswerEval() {
    setTriggeringEval(true);
    setEvalError('');
    const res = await authedFetch('/api/admin/eval/chat-answer/trigger', { method: 'POST' });
    setTriggeringEval(false);

    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setEvalError(body.detail || 'Failed to run the chat-answer eval.');
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

  async function handleTriggerEvidenceSelectionEval() {
    setTriggeringEvidenceSelectionEval(true);
    setEvidenceSelectionEvalError('');
    const res = await authedFetch('/api/admin/eval/evidence-selection/trigger', { method: 'POST' });
    setTriggeringEvidenceSelectionEval(false);

    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setEvidenceSelectionEvalError(body.detail || 'Failed to run the evidence-selection eval.');
      return;
    }
    loadEvalRuns();
  }

  // Shared by both "Judge drift" dropdown entries - which eval_type to diff is the only
  // thing that differs between them (see evalTypeConfig below).
  async function handleTriggerJudgeDrift(evalType) {
    setTriggeringJudgeDrift(true);
    setJudgeDriftEvalError('');
    const res = await authedFetch(`/api/admin/eval/judge-drift/trigger?eval_type=${evalType}`, { method: 'POST' });
    setTriggeringJudgeDrift(false);

    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setJudgeDriftEvalError(body.detail || 'Failed to run the judge-drift check.');
      return;
    }
    loadEvalRuns();
  }

  async function handleTriggerFeedSummaryEval() {
    setTriggeringFeedSummaryEval(true);
    setFeedSummaryEvalError('');
    const res = await authedFetch('/api/admin/eval/feed-summary/trigger', { method: 'POST' });
    setTriggeringFeedSummaryEval(false);

    if (res.status === 403) {
      setForbidden(true);
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setFeedSummaryEvalError(body.detail || 'Failed to run the feed-summary eval.');
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
    setRunsOffset(0);
    loadRuns(0);
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

  useEffect(() => {
    if (user) {
      loadMonitorSamples();
    }
  }, [user, monitorFilterType, monitorFlaggedOnly, monitorReviewedFilter]);

  // Backs the Evaluation section's unified dropdown+button toolbar - each entry's
  // trigger/triggering/error come from that eval type's own existing state/handler
  // (unchanged), this just dispatches to the right one based on evalFilterType.
  const evalTypeConfig = {
    chat_answer: {
      description:
        'Judges chat-answer synthesis for groundedness and completeness, on a fixed set of (question, sample facts) pairs answered fresh each run via synthesize_insight() directly - not the live retrieval/routing agent, so results reflect the synthesis prompt, not whatever retrieval happens to find. See eval/runners/run_chat_answer_eval.py for why.',
      trigger: handleTriggerChatAnswerEval,
      triggering: triggeringEval,
      error: evalError,
    },
    insight: {
      description:
        'Judges the pipeline’s own insight synthesis for groundedness and completeness, on a fixed set of (ticker, evidence) pairs synthesized fresh each run - not real ticker_insights rows, so results reflect the prompt, not whatever news exists right now.',
      trigger: handleTriggerInsightEval,
      triggering: triggeringInsightEval,
      error: insightEvalError,
    },
    feed_summary: {
      description:
        'Judges the one-sentence "why is this relevant" summary custom and common feed items get, on a fixed set of (article, feed) pairs, using the exact same summarization function the live pipeline calls.',
      trigger: handleTriggerFeedSummaryEval,
      triggering: triggeringFeedSummaryEval,
      error: feedSummaryEvalError,
    },
    classification: {
      description:
        'Scores how accurately news gets matched to the right common feed, using precision, recall, and false-skip-rate against a hand-labeled sample. Scoped to common feeds only - custom feeds have no single sitewide threshold to tune toward.',
      trigger: handleTriggerClassificationEval,
      triggering: triggeringClassificationEval,
      error: classificationEvalError,
    },
    guardrails: {
      description:
        'Measures how well each guardrail layer catches bad content versus wrongly blocking legitimate requests, for both the regex and LLM layers.',
      trigger: handleTriggerGuardrailEval,
      triggering: triggeringGuardrailEval,
      error: guardrailEvalError,
    },
    evidence_selection: {
      description:
        'Checks whether decide_feed_sources() correctly decides which supplementary sources (financial reports, peer-industry news) a feed needs, per feed type, against a hand-labeled sample. Deterministic scoring - no judge LLM.',
      trigger: handleTriggerEvidenceSelectionEval,
      triggering: triggeringEvidenceSelectionEval,
      error: evidenceSelectionEvalError,
    },
    judge_drift_feed_summary: {
      description:
        'Diffs the latest feed-summary eval run against the one before it, item by item, flagging groundedness/completeness swings for human review. Never auto-blocks - see eval/run_judge_drift_check.py.',
      trigger: () => handleTriggerJudgeDrift('feed_summary'),
      triggering: triggeringJudgeDrift,
      error: judgeDriftEvalError,
    },
    judge_drift_insight_quality: {
      description:
        'Same judge-drift check as above, but for the insight-synthesis eval instead of feed-summary.',
      trigger: () => handleTriggerJudgeDrift('insight_quality'),
      triggering: triggeringJudgeDrift,
      error: judgeDriftEvalError,
    },
  };

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
          <div className="inline-form">
            <label>
              From
              <input type="date" value={runsStartDate} onChange={(e) => setRunsStartDate(e.target.value)} />
            </label>
            <label>
              To
              <input type="date" value={runsEndDate} onChange={(e) => setRunsEndDate(e.target.value)} />
            </label>
            <button type="button" onClick={handleRunsFilterChange}>Filter</button>
          </div>
          {runs.length === 0 ? (
            <p>No runs in this range.</p>
          ) : (
            <ul className="admin-runs admin-runs-scroll">
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
          <div className="inline-form">
            <button type="button" onClick={handleRunsPrevPage} disabled={runsOffset === 0}>
              Newer
            </button>
            <button type="button" onClick={handleRunsNextPage} disabled={runs.length < RUNS_PAGE_SIZE}>
              Older
            </button>
          </div>
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
          </p>
        </section>

        <section>
          <h2>Output quality, guardrail &amp; classification monitoring (continuous sampling)</h2>
          <p className="info">
            Continuously samples up to 10% (capped at 20) of recent business-metric output (custom/common
            feed summaries, pipeline insights, chat answers), both advice-avoidance guardrails, and feed
            classification decisions, and judges each the same way the Evaluation section scores them -
            real production output instead of a fixed test set. A business-metric sample is flagged when
            it&apos;s not fully grounded (zero tolerance on unsupported claims) or completeness falls below
            80%; a guardrail or classification sample is flagged when the independent evaluation judge
            disagrees with the live decision (the guardrail&apos;s regex/LLM layers, or the classifier&apos;s
            embedding-similarity match). Uses its own time window below, separate from the Monitoring
            section&apos;s - sampling reads each source table directly rather than the cost/latency
            aggregates that window drives. Output guardrail sampling can only audit passed responses - a
            blocked response&apos;s text is never persisted, so this catches missed violations, not
            re-litigating what was already blocked.
          </p>
          <div className="admin-toolbar">
            <div className="admin-toolbar-row sampling">
              <span className="admin-row-eyebrow">Sampling</span>
              <div className="admin-row-controls" style={{ marginLeft: 'auto' }}>
                <span className="admin-field-label">Window</span>
                <select
                  className="admin-ctl active"
                  value={monitorSampleWindow}
                  onChange={(e) => setMonitorSampleWindow(e.target.value)}
                >
                  <option value="24h">Last 24 hours</option>
                  <option value="7d">Last 7 days</option>
                  <option value="30d">Last 30 days</option>
                </select>
                <button
                  type="button"
                  className="admin-btn-primary"
                  onClick={handleTriggerSampling}
                  disabled={triggeringSampling}
                >
                  {triggeringSampling ? 'Sampling...' : 'Run sampling now'}
                </button>
              </div>
            </div>

            <div className="admin-toolbar-row filters">
              <span className="admin-row-eyebrow">
                Filter results
                {monitorActiveFilterCount > 0 && <span className="admin-filter-count">{monitorActiveFilterCount}</span>}
              </span>
              <div className="admin-row-controls">
                <select
                  className="admin-ctl"
                  value={monitorFilterType}
                  onChange={(e) => setMonitorFilterType(e.target.value)}
                >
                  <option value="">All biz metrics</option>
                  <option value="feed_combine">Feed summary</option>
                  <option value="insight">Insight</option>
                  <option value="chat_answer">Chat answer</option>
                  <option value="guardrail_input">Input guardrail</option>
                  <option value="guardrail_output">Output guardrail</option>
                  <option value="guardrail_all">All guardrails</option>
                  <option value="classification_custom_feed">Custom feed classification</option>
                  <option value="classification_common_feed">Common feed classification</option>
                  <option value="classification_all">All classification</option>
                </select>

                <div className="admin-search-wrap">
                  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
                    <circle cx="5.5" cy="5.5" r="4.3" stroke="currentColor" strokeWidth="1.3" />
                    <path d="M9 9l3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                  </svg>
                  <input
                    className="admin-ctl"
                    value={monitorTickerFilter}
                    onChange={(e) => setMonitorTickerFilter(e.target.value)}
                    placeholder="Ticker, e.g. CBA.AX"
                  />
                </div>

                <div className="admin-date-range">
                  <input type="date" value={monitorStartDate} onChange={(e) => setMonitorStartDate(e.target.value)} />
                  <span className="sep">-</span>
                  <input type="date" value={monitorEndDate} onChange={(e) => setMonitorEndDate(e.target.value)} />
                </div>

                <select
                  className="admin-ctl"
                  value={monitorReviewedFilter}
                  onChange={(e) => setMonitorReviewedFilter(e.target.value)}
                >
                  <option value="">Any review status</option>
                  <option value="to_review">To review</option>
                  <option value="reviewed">Reviewed</option>
                </select>

                <button
                  type="button"
                  className={`admin-toggle-chip${monitorFlaggedOnly ? ' on' : ''}`}
                  onClick={() => setMonitorFlaggedOnly(!monitorFlaggedOnly)}
                >
                  <span className="dot" />
                  Flagged only
                </button>

                <button type="button" className="admin-btn-text" onClick={loadMonitorSamples}>
                  Filter
                </button>
                {monitorActiveFilterCount > 0 && (
                  <button type="button" className="admin-btn-text" onClick={handleClearMonitorFilters}>
                    Clear
                  </button>
                )}
              </div>
            </div>
          </div>
          {samplingError && <p className="error">{samplingError}</p>}

          {monitorSamples.length === 0 ? (
            <p>No samples yet.</p>
          ) : (
            <div className="quality-sample-list">
              {monitorSamples.map((s) => {
                if (s._kind === 'guardrail') {
                  return <GuardrailSampleCard key={s.id} sample={s} onReview={handleReviewSample} />;
                }
                if (s._kind === 'classification') {
                  return <ClassificationSampleCard key={s.id} sample={s} onReview={handleReviewSample} />;
                }
                return <QualitySampleCard key={s.id} sample={s} onReview={handleReviewSample} />;
              })}
            </div>
          )}
        </section>

        <section>
          <h2>Evaluation</h2>
          <p className="info">
            One eval type at a time, picked below - each reuses the exact function the live system
            runs, so a score here and a production gate can never quietly drift apart. Fixed test
            sets, so no filters here (unlike the Monitoring panel above) - the button re-runs
            whichever type is selected and shows that run&apos;s per-item results as cards, same
            3-column format as Monitoring.
          </p>

          <div className="admin-toolbar">
            <div className="admin-toolbar-row filters">
              <span className="admin-row-eyebrow">Eval type</span>
              <select
                className="admin-ctl"
                value={evalFilterType}
                onChange={(e) => setEvalFilterType(e.target.value)}
              >
                <option value="chat_answer">Chat answer quality</option>
                <option value="insight">Insight quality</option>
                <option value="feed_summary">Feed summary quality</option>
                <option value="classification">Classification quality</option>
                <option value="guardrails">Guardrail effectiveness</option>
                <option value="evidence_selection">Evidence selection</option>
                <option value="judge_drift_feed_summary">Judge drift – feed summary</option>
                <option value="judge_drift_insight_quality">Judge drift – insight quality</option>
              </select>
              <button
                type="button"
                className="admin-btn-primary"
                onClick={evalTypeConfig[evalFilterType].trigger}
                disabled={evalTypeConfig[evalFilterType].triggering}
              >
                {evalTypeConfig[evalFilterType].triggering ? 'Running...' : 'Run eval now'}
              </button>
            </div>
          </div>
          <p className="info">{evalTypeConfig[evalFilterType].description}</p>
          {evalTypeConfig[evalFilterType].error && (
            <p className="error">{evalTypeConfig[evalFilterType].error}</p>
          )}
          {evalTypeConfig[evalFilterType].triggering && (
            <p className="info">
              Running a fresh evaluation now (real LLM calls - this can take a minute or two). The
              results below are still the PREVIOUS run until this one finishes and the page refreshes.
            </p>
          )}

          <div
            style={
              evalTypeConfig[evalFilterType].triggering
                ? { opacity: 0.45, pointerEvents: 'none' }
                : undefined
            }
          >
          {evalFilterType === 'chat_answer' && (
            chatAnswerRuns.length === 0 ? (
              <p>No chat-answer eval runs yet.</p>
            ) : (
              <>
                <p className="info">
                  Latest run ({new Date(chatAnswerRuns[0].created_at).toLocaleString()}):{' '}
                  {chatAnswerRuns[0].summary.summary.n_total} questions judged,{' '}
                  {chatAnswerRuns[0].summary.summary.pct_grounded ?? 'n/a'}% fully grounded, avg groundedness{' '}
                  {chatAnswerRuns[0].summary.summary.avg_groundedness_pct ?? 'n/a'}%, avg completeness{' '}
                  {chatAnswerRuns[0].summary.summary.avg_completeness_pct ?? 'n/a'}%.
                </p>
                <div className="quality-sample-list">
                  {chatAnswerRuns[0].summary.results.map((item, i) => (
                    <ChatAnswerEvalItemCard key={i} item={item} />
                  ))}
                </div>
              </>
            )
          )}

          {evalFilterType === 'insight' && (
            insightRuns.length === 0 ? (
              <p>No insight eval runs yet.</p>
            ) : (
              <>
                <p className="info">
                  Latest run ({new Date(insightRuns[0].created_at).toLocaleString()}):{' '}
                  {insightRuns[0].summary.summary.n_total} insights judged,{' '}
                  {insightRuns[0].summary.summary.pct_grounded ?? 'n/a'}% grounded,{' '}
                  {insightRuns[0].summary.summary.avg_completeness_pct ?? 'n/a'}% avg completeness.
                </p>
                <div className="quality-sample-list">
                  {insightRuns[0].summary.results.map((item, i) => (
                    <InsightEvalItemCard key={i} item={item} />
                  ))}
                </div>
              </>
            )
          )}

          {evalFilterType === 'feed_summary' && (
            feedSummaryRuns.length === 0 ? (
              <p>No feed-summary eval runs yet.</p>
            ) : (
              <>
                <p className="info">
                  Latest run ({new Date(feedSummaryRuns[0].created_at).toLocaleString()}):{' '}
                  {feedSummaryRuns[0].summary.summary.n_total} pairs judged,{' '}
                  {feedSummaryRuns[0].summary.summary.pct_grounded ?? 'n/a'}% fully grounded, avg groundedness{' '}
                  {feedSummaryRuns[0].summary.summary.avg_groundedness_pct ?? 'n/a'}%, avg completeness{' '}
                  {feedSummaryRuns[0].summary.summary.avg_completeness_pct ?? 'n/a'}%.
                </p>
                <div className="quality-sample-list">
                  {feedSummaryRuns[0].summary.results.map((item, i) => (
                    <FeedSummaryEvalItemCard key={i} item={item} />
                  ))}
                </div>
              </>
            )
          )}

          {evalFilterType === 'classification' && (
            classificationRuns.length === 0 ? (
              <p>No classification eval runs yet.</p>
            ) : (
              <>
                <p className="info">
                  Latest run ({new Date(classificationRuns[0].created_at).toLocaleString()}):{' '}
                  threshold {classificationRuns[0].summary.results[0].threshold ?? 'as-deployed'}{' '}
                  (deployed: {(classificationRuns[0].summary.results[0].deployed_thresholds || []).join(', ') || 'n/a'},
                  n={classificationRuns[0].summary.results[0].n}), precision{' '}
                  {classificationRuns[0].summary.results[0].precision ?? 'n/a'}, recall{' '}
                  {classificationRuns[0].summary.results[0].recall ?? 'n/a'}, false-skip rate{' '}
                  {classificationRuns[0].summary.results[0].false_skip_rate ?? 'n/a'}
                  {classificationRuns[0].summary.pr_auc &&
                    ` - PR AUC ${classificationRuns[0].summary.pr_auc.auc ?? 'n/a'}`}
                  .
                </p>
                <ClassificationThresholdPanel summary={classificationRuns[0].summary} />
                {classificationRuns[0].summary.results[0].rows ? (
                  <div className="quality-sample-list">
                    {classificationRuns[0].summary.results[0].rows.map((item, i) => (
                      <ClassificationEvalItemCard key={i} item={item} />
                    ))}
                  </div>
                ) : (
                  <p>This run predates per-item detail - re-run to see item cards.</p>
                )}
              </>
            )
          )}

          {evalFilterType === 'guardrails' && (
            guardrailRuns.length === 0 ? (
              <p>No guardrail eval runs yet.</p>
            ) : (
              <>
                <p className="info">
                  Latest run ({new Date(guardrailRuns[0].created_at).toLocaleString()}) - Input regex: TPR{' '}
                  {guardrailRuns[0].summary.summary.input_guardrail.regex_layer.true_positive_rate ?? 'n/a'}, FPR{' '}
                  {guardrailRuns[0].summary.summary.input_guardrail.regex_layer.false_positive_rate ?? 'n/a'};
                  LLM: TPR {guardrailRuns[0].summary.summary.input_guardrail.llm_layer.true_positive_rate ?? 'n/a'},
                  FPR {guardrailRuns[0].summary.summary.input_guardrail.llm_layer.false_positive_rate ?? 'n/a'}.
                  Output regex: TPR{' '}
                  {guardrailRuns[0].summary.summary.output_guardrail.regex_layer.true_positive_rate ?? 'n/a'}, FPR{' '}
                  {guardrailRuns[0].summary.summary.output_guardrail.regex_layer.false_positive_rate ?? 'n/a'};
                  LLM: TPR {guardrailRuns[0].summary.summary.output_guardrail.llm_layer.true_positive_rate ?? 'n/a'},
                  FPR {guardrailRuns[0].summary.summary.output_guardrail.llm_layer.false_positive_rate ?? 'n/a'}.
                </p>

                <h4>Input guardrail (advice-seeking questions)</h4>
                {!guardrailRuns[0].summary.summary.input_guardrail.regex_layer.rows ? (
                  <p>This run predates per-item detail - re-run to see item cards.</p>
                ) : (
                  <div className="quality-sample-list">
                    {guardrailRuns[0].summary.summary.input_guardrail.regex_layer.rows.map((regexRow, i) => {
                      const llmRow = guardrailRuns[0].summary.summary.input_guardrail.llm_layer.rows[i];
                      return (
                        <GuardrailEvalItemCard
                          key={i}
                          text={regexRow.text}
                          isBad={regexRow.is_bad}
                          regexPredicted={regexRow.predicted_bad}
                          llmPredicted={llmRow.predicted_bad}
                        />
                      );
                    })}
                  </div>
                )}

                <h4>Output guardrail (advice-giving answers)</h4>
                {!guardrailRuns[0].summary.summary.output_guardrail.regex_layer.rows ? (
                  <p>This run predates per-item detail - re-run to see item cards.</p>
                ) : (
                  <div className="quality-sample-list">
                    {guardrailRuns[0].summary.summary.output_guardrail.regex_layer.rows.map((regexRow, i) => {
                      const llmRow = guardrailRuns[0].summary.summary.output_guardrail.llm_layer.rows[i];
                      return (
                        <GuardrailEvalItemCard
                          key={i}
                          text={regexRow.text}
                          isBad={regexRow.is_bad}
                          regexPredicted={regexRow.predicted_bad}
                          llmPredicted={llmRow.predicted_bad}
                        />
                      );
                    })}
                  </div>
                )}
              </>
            )
          )}

          {evalFilterType === 'evidence_selection' && (
            evidenceSelectionRuns.length === 0 ? (
              <p>No evidence-selection eval runs yet.</p>
            ) : (
              <>
                <p className="info">
                  Latest run ({new Date(evidenceSelectionRuns[0].created_at).toLocaleString()}):{' '}
                  {evidenceSelectionRuns[0].summary.summary.n_feeds} feeds scored, needs_reports accuracy{' '}
                  {evidenceSelectionRuns[0].summary.summary.needs_reports_accuracy ?? 'n/a'}, needs_peer_news
                  accuracy {evidenceSelectionRuns[0].summary.summary.needs_peer_news_accuracy ?? 'n/a'}, exact
                  match {evidenceSelectionRuns[0].summary.summary.exact_match_accuracy ?? 'n/a'}.
                </p>
                <div className="quality-sample-list">
                  {evidenceSelectionRuns[0].summary.results.map((item, i) => (
                    <EvidenceSelectionEvalItemCard key={i} item={item} />
                  ))}
                </div>
              </>
            )
          )}

          {evalFilterType === 'judge_drift_feed_summary' && (
            <JudgeDriftReport report={judgeDriftRuns.find((r) => r.summary.eval_type === 'feed_summary')?.summary} />
          )}

          {evalFilterType === 'judge_drift_insight_quality' && (
            <JudgeDriftReport
              report={judgeDriftRuns.find((r) => r.summary.eval_type === 'insight_quality')?.summary}
            />
          )}
          </div>
        </section>
      </main>
    </div>
  );
}
