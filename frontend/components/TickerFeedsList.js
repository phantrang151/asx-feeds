import { useState } from 'react';
import { supabase } from '../lib/supabaseClient';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// 10%-90% in steps of 10 - the only granularity the backend accepts (see
// FeedUpdateRequest in app/main.py).
const THRESHOLD_OPTIONS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];

export default function TickerFeedsList({ tickers, feeds, onFeedDeleted, onTickerDeleted, onFeedUpdated }) {
  const [editingFeedId, setEditingFeedId] = useState(null);
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editError, setEditError] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);

  async function authedFetch(path, options) {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    return fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${session.access_token}`,
        ...(options && options.headers),
      },
    });
  }

  function startEdit(feed) {
    setEditingFeedId(feed.id);
    setEditName(feed.feed_name);
    setEditDescription(feed.feed_description);
    setEditError('');
  }

  function cancelEdit() {
    setEditingFeedId(null);
    setEditError('');
  }

  async function handleSaveEdit(e, feedId) {
    e.preventDefault();
    setEditError('');
    setSavingEdit(true);

    let res;
    try {
      res = await authedFetch(`/api/feeds/${feedId}`, {
        method: 'PATCH',
        body: JSON.stringify({ feed_name: editName, feed_description: editDescription }),
      });
    } catch (err) {
      setSavingEdit(false);
      setEditError('Could not reach the API - is it running on ' + API_URL + '?');
      return;
    }

    setSavingEdit(false);

    if (!res.ok) {
      const resBody = await res.json().catch(() => ({}));
      setEditError(resBody.detail || 'Failed to update feed.');
      return;
    }

    setEditingFeedId(null);
    onFeedUpdated();
  }

  async function handleThresholdChange(feedId, value) {
    const res = await authedFetch(`/api/feeds/${feedId}`, {
      method: 'PATCH',
      body: JSON.stringify({ match_threshold: parseFloat(value) }),
    });
    if (!res.ok) {
      const resBody = await res.json().catch(() => ({}));
      window.alert(resBody.detail || 'Failed to update threshold.');
      return;
    }
    onFeedUpdated();
  }

  async function handleRefresh(feedId) {
    const res = await authedFetch(`/api/feeds/${feedId}/refresh`, { method: 'POST' });
    if (!res.ok) {
      const resBody = await res.json().catch(() => ({}));
      window.alert(resBody.detail || 'Failed to queue refresh.');
      return;
    }
    onFeedUpdated();
  }

  async function handleDeleteFeed(feedId) {
    if (!window.confirm('Delete this feed? Its alert history will be deleted too.')) return;
    const { error } = await supabase.from('feeds').delete().eq('id', feedId);
    if (error) {
      window.alert(error.message);
      return;
    }
    onFeedDeleted();
  }

  async function handleDeleteTicker(ticker) {
    if (!window.confirm(`Delete ${ticker} and all of its feeds? This can't be undone.`)) return;

    const {
      data: { user },
    } = await supabase.auth.getUser();

    // Feeds first, then the watchlist row: feeds.ticker isn't FK'd to watchlist_stocks,
    // so deleting the watchlist row alone would silently orphan this user's feeds for
    // this ticker. If the second delete fails, the ticker stays listed with no feeds
    // under it - a visible, re-triggerable state - rather than the reverse (orphaned
    // feeds with no ticker row left to attach a delete button to).
    const { error: feedsError } = await supabase.from('feeds').delete().eq('user_id', user.id).eq('ticker', ticker);
    if (feedsError) {
      window.alert(feedsError.message);
      return;
    }

    const { error: watchlistError } = await supabase
      .from('watchlist_stocks')
      .delete()
      .eq('user_id', user.id)
      .eq('ticker', ticker);
    if (watchlistError) {
      window.alert(watchlistError.message);
      return;
    }

    onTickerDeleted();
  }

  if (!tickers.length) {
    return <p>No tickers yet - add one on the left to get started.</p>;
  }

  return (
    <ul className="ticker-feeds-list">
      {tickers.map((t) => {
        const tickerFeeds = feeds.filter((f) => f.ticker === t.ticker);
        return (
          <li key={t.id}>
            <div className="ticker-feeds-header">
              <strong>{t.ticker}</strong>
              <span>{t.company_name}</span>
              <button type="button" className="delete-button" onClick={() => handleDeleteTicker(t.ticker)}>
                Delete ticker
              </button>
            </div>
            {tickerFeeds.length ? (
              <ul className="feed-list">
                {tickerFeeds.map((f) => (
                  <li key={f.id}>
                    {editingFeedId === f.id ? (
                      <form className="stacked-form feed-edit-form" onSubmit={(e) => handleSaveEdit(e, f.id)}>
                        <label>
                          Feed name
                          <input value={editName} onChange={(e) => setEditName(e.target.value)} required />
                        </label>
                        <label>
                          Feed description
                          <textarea
                            value={editDescription}
                            onChange={(e) => setEditDescription(e.target.value)}
                            required
                            rows={3}
                          />
                        </label>
                        <div className="feed-edit-actions">
                          <button type="submit" disabled={savingEdit}>
                            {savingEdit ? 'Saving...' : 'Save'}
                          </button>
                          <button type="button" onClick={cancelEdit}>
                            Cancel
                          </button>
                        </div>
                        {editError && <p className="error">{editError}</p>}
                      </form>
                    ) : (
                      <>
                        <div className="feed-main">
                          <strong>{f.feed_name}</strong> - {f.feed_description}
                        </div>
                        {f.feed_type === 'custom' && (
                          <div className="feed-controls">
                            <select
                              value={String(Math.round(f.match_threshold * 10) / 10)}
                              onChange={(e) => handleThresholdChange(f.id, e.target.value)}
                              title="Relevance threshold"
                            >
                              {THRESHOLD_OPTIONS.map((opt) => (
                                <option key={opt} value={String(opt)}>
                                  {Math.round(opt * 100)}%
                                </option>
                              ))}
                            </select>
                            <button type="button" onClick={() => startEdit(f)}>
                              Edit
                            </button>
                            <button type="button" disabled={f.needs_rematch} onClick={() => handleRefresh(f.id)}>
                              {f.needs_rematch ? 'Refresh queued' : 'Refresh'}
                            </button>
                          </div>
                        )}
                        <button type="button" className="delete-button" onClick={() => handleDeleteFeed(f.id)}>
                          Delete feed
                        </button>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="info">No feeds for this ticker yet.</p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
