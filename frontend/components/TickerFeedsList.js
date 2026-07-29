export default function TickerFeedsList({ tickers, feeds }) {
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
            </div>
            {tickerFeeds.length ? (
              <ul className="feed-list">
                {tickerFeeds.map((f) => (
                  <li key={f.id}>
                    <strong>{f.feed_name}</strong> - {f.feed_description}
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
