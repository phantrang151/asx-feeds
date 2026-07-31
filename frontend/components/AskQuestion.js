import { useState } from 'react';
import { supabase } from '../lib/supabaseClient';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function AnswerBlock({ question, answer, references }) {
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
      <p className="qa-answer">{answer}</p>
    </>
  );
}

export default function AskQuestion() {
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
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. Why is Telstra's profit increasing? TLS.AX"
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
          <p className="qa-placeholder">Ask something above - the answer will show up here.</p>
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
