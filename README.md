# Ticker Indicator Tracker

A small local dashboard for tracking a watchlist of tickers against three
momentum oscillators: Williams %R, RSI, and Stochastic %K/%D. It flags each
ticker as Neutral, Watch, Buy/Sell, or Strong Buy/Sell based on how many of
the three indicators are in oversold or overbought territory. You check it
on your own schedule; it doesn't send notifications.

## Setup

1. Install Python 3.10 or newer.
2. In this folder, install dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Run the app:

   ```
   streamlit run app.py
   ```

   It opens automatically in your browser, usually at `http://localhost:8501`.

## Using it

- **Add tickers** in the sidebar (any symbol Yahoo Finance recognizes, e.g. `AAPL`, `TSLA`, `NVDA`).
- Tickers persist between runs in `watchlist.json` in this folder.
- **Thresholds** for each indicator are adjustable sliders in the sidebar.
  Defaults are the standard levels: Williams %R oversold at -80 / overbought
  at -20, RSI at 30/70, Stochastic at 20/80.
- The main table shows the latest reading for each ticker and a combined
  Signal. "Strong Buy/Sell" means all three indicators agree; "Watch" means
  only one does.
- Pick a ticker under "Detail view" to see its price chart alongside each
  indicator, with your threshold lines drawn in.
- **Refresh data** in the sidebar clears the 5-minute data cache and re-pulls
  prices. Daily bars don't need refreshing more often than that.

## Notes and limitations

- Price data comes from Yahoo Finance via the `yfinance` library, which is
  unofficial and occasionally breaks when Yahoo changes something on their
  end. If tickers stop loading, try `pip install --upgrade yfinance`.
- This is signal *surfacing*, not trading advice or automated execution.
  Nothing here places trades or predicts outcomes; it just flags when
  price is at a statistical extreme relative to its recent range, which is
  a starting point for your own judgment, not a conclusion.
- All indicators use daily bars. Intraday tracking would need a different
  data source and closer attention to API rate limits.
