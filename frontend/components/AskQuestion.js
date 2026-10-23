import { useRef, useState } from 'react';
import { supabase } from '../lib/supabaseClient';
import MarkdownText from './MarkdownText';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function AnswerBlock({ question, answer, references }) {
  return (
    <>
      <p className="qa-question">{question}</p>
      <p className="qa-disclaimer">
        ⚠ AI-generated answer - please verify against the references below before relying on it.
      </p>
      {references.length > 0 && (
        <div className="qa-references">
          <p className="qa-references-title">References used for this answer:</p>
          <ul>
            {references.map((ref, i) => (
              <li key={i}>
                {ref.url ? (
                  <a href={ref.url} target="_blank" rel="noreferrer">
                    {ref.content}
                  </a>
                ) : (
                  ref.content
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      <MarkdownText className="qa-answer" text={answer} />
    </>
  );
}

// Shown in the empty answer box. Only questions the chat can actually answer today: each is
// about one ticker's thesis, which get_my_thesis_tool reads (questions spanning every tracked
// company aren't supported yet). The full ticker (e.g. NAB.AX) keeps the router unambiguous.
function sampleQuestions(ticker) {
  return [
    { category: 'My investment thesis', question: `What has changed in my ${ticker} investment thesis?` },
    { category: 'My feeds and insights', question: `Are there any contradictions across my ${ticker} feeds?` },
    {
      category: 'Historical comparisons',
      question: `Which of my previous ${ticker} conclusions are no longer supported?`,
    },
  ];
}

export default function AskQuestion({ sampleTicker = null }) {
  const inputRef = useRef(null);
  const [threadId] = useState(() => crypto.randomUUID());
  const [question, setQuestion] = useState('');
  const [current, setCurrent] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState('');
  const [asking, setAsking] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setAsking(true);
    const askedQuestion = question;

    const {
      data: { session },
    } = await supabase.auth.getSession();

    if (!session) {
      setAsking(false);
      setError('Your session has expired - please sign in again.');
      return;
    }

    let res;
    try {
      res = await fetch(`${API_URL}/api/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ question: askedQuestion, thread_id: threadId }),
      });
    } catch (err) {
      setAsking(false);
      setError('Could not reach the API - is it running on ' + API_URL + '?');
      return;
    }

    setAsking(false);

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(body.detail || 'Failed to get an answer.');
      return;
    }

    const data = await res.json();
    setHistory((h) => (current ? [current, ...h] : h));
    setCurrent({ question: askedQuestion, answer: data.answer, references: data.references || [] });
    setQuestion('');
  }

  return (
    <div>
      <form onSubmit={handleSubmit} className="inline-form">
        <input
          ref={inputRef}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about one of your tickers"
          required
        />
        <button type="submit" disabled={asking || !question.trim()}>
          {asking ? 'Thinking...' : 'Ask'}
        </button>
      </form>
      {error && <p className="error">{error}</p>}

      <div className="qa-answer-box">
        {asking ? (
          <p className="qa-placeholder">Thinking...</p>
        ) : current ? (
          <AnswerBlock question={current.question} answer={current.answer} references={current.references} />
        ) : (
          <div className="qa-samples">
            {sampleTicker ? (
              <>
                <p className="qa-placeholder">Ask something above, or try one of these about your thesis:</p>
                <div className="qa-sample-list">
                  {sampleQuestions(sampleTicker).map(({ category, question: q }) => (
                    <button
                      key={q}
                      type="button"
                      className="qa-sample"
                      onClick={() => {
                        // Fill in rather than send, so the question can be edited first.
                        setQuestion(q);
                        inputRef.current?.focus();
                      }}
                    >
                      <span className="qa-sample-category">{category}</span>
                      <span className="qa-sample-question">{q}</span>
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <p className="qa-placeholder">
                Ask something above - the answer will show up here. Add a ticker and a feed below to ask
                about your own thesis.
              </p>
            )}
          </div>
        )}
      </div>

      {history.length > 0 && (
        <details className="qa-history">
          <summary>Previous questions ({history.length})</summary>
          <ul className="qa-list">
            {history.map((qa, i) => (
              <li key={i}>
                <AnswerBlock question={qa.question} answer={qa.answer} references={qa.references} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
