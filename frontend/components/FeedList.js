export default function FeedList({ feeds }) {
  if (!feeds.length) {
    return <p>No feeds yet - add a ticker, then create a feed above.</p>;
  }

  return (
    <ul className="feed-list">
      {feeds.map((f) => (
        <li key={f.id}>
          <strong>{f.feed_name}</strong> ({f.ticker}) - {f.feed_description}
        </li>
      ))}
    </ul>
  );
}
