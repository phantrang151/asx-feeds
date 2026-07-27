export default function TickerList({ tickers }) {
  if (!tickers.length) {
    return <p>No tickers yet - add one above.</p>;
  }

  return (
    <ul className="ticker-list">
      {tickers.map((t) => (
        <li key={t.id}>
          {t.ticker} - {t.company_name}
        </li>
      ))}
    </ul>
  );
}
