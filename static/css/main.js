function addToWatchlist(ticker) {
  fetch('/add_to_watchlist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol: ticker })
  }).then(res => res.json())
    .then(data => alert(data.status === 'success' ? 'Added to watchlist!' : data.msg));
}
