import { useState } from 'react';
import { supabase } from '../lib/supabaseClient';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
    setCurrent({ question: askedQuestion, answer: data.answer });
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
          <>
            <p className="qa-question">{current.question}</p>
            <p className="qa-answer">{current.answer}</p>
          </>
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
                <p className="qa-question">{qa.question}</p>
                <p className="qa-answer">{qa.answer}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
