"""
Ticker Indicator Tracker
------------------------
A simple local dashboard: add tickers, see Williams %R, RSI, and Stochastic
readings for each, and get a plain-language signal (Buy/Sell/Neutral) based
on how many of the three indicators are in oversold or overbought territory.

Run with:
    streamlit run app.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

WATCHLIST_FILE = Path(__file__).parent / "watchlist.json"
DEFAULT_TICKERS = ["AAPL", "MSFT"]

# ---------------------------------------------------------------------------
# Persistence — keep the watchlist between runs without needing a database
# ---------------------------------------------------------------------------

def load_watchlist():
    if WATCHLIST_FILE.exists():
        try:
            return json.loads(WATCHLIST_FILE.read_text())
        except Exception:
            return DEFAULT_TICKERS.copy()
    return DEFAULT_TICKERS.copy()


def save_watchlist(tickers):
    WATCHLIST_FILE.write_text(json.dumps(tickers, indent=2))


# ---------------------------------------------------------------------------
# Indicators — plain pandas, no extra TA library required
# ---------------------------------------------------------------------------

def williams_r(df, period=14):
    highest_high = df["High"].rolling(period).max()
    lowest_low = df["Low"].rolling(period).min()
    wr = (highest_high - df["Close"]) / (highest_high - lowest_low) * -100
    return wr.replace([np.inf, -np.inf], np.nan)


def rsi(df, period=14):
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    out = 100 - (100 / (1 + rs))
    return out.replace([np.inf, -np.inf], 100)


def stochastic(df, k_period=14, d_period=3, smooth_k=3):
    lowest_low = df["Low"].rolling(k_period).min()
    highest_high = df["High"].rolling(k_period).max()
    raw_k = (df["Close"] - lowest_low) / (highest_high - lowest_low) * 100
    k = raw_k.rolling(smooth_k).mean().replace([np.inf, -np.inf], np.nan)
    d = k.rolling(d_period).mean()
    return k, d


def build_indicator_frame(df):
    out = df.copy()
    out["WilliamsR"] = williams_r(out)
    out["RSI"] = rsi(out)
    out["StochK"], out["StochD"] = stochastic(out)
    return out


def classify_signal(wr, rsi_val, stoch_k, t):
    oversold = 0
    overbought = 0
    if wr <= t["wr_oversold"]:
        oversold += 1
    elif wr >= t["wr_overbought"]:
        overbought += 1
    if rsi_val <= t["rsi_oversold"]:
        oversold += 1
    elif rsi_val >= t["rsi_overbought"]:
        overbought += 1
    if stoch_k <= t["stoch_oversold"]:
        oversold += 1
    elif stoch_k >= t["stoch_overbought"]:
        overbought += 1

    if oversold >= 3:
        return "Strong Buy", 3
    if oversold == 2:
        return "Buy", 2
    if oversold == 1:
        return "Watch (oversold)", 1
    if overbought >= 3:
        return "Strong Sell", -3
    if overbought == 2:
        return "Sell", -2
    if overbought == 1:
        return "Watch (overbought)", -1
    return "Neutral", 0


SIGNAL_COLORS = {
    "Strong Buy": "#1a7f37",
    "Buy": "#4caf50",
    "Watch (oversold)": "#9ccc9a",
    "Neutral": "#8a8a8a",
    "Watch (overbought)": "#eba39a",
    "Sell": "#e57373",
    "Strong Sell": "#c62828",
}

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def fetch_data(ticker, period):
    df = yf.download(ticker, period=period, interval="1d", progress=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Ticker Indicator Tracker", layout="wide")
st.title("Ticker Indicator Tracker")
st.caption("Williams %R, RSI, and Stochastic, checked on your own schedule. No automated alerts.")

if "tickers" not in st.session_state:
    st.session_state.tickers = load_watchlist()

with st.sidebar:
    st.header("Watchlist")
    with st.form("add_ticker_form", clear_on_submit=True):
        new_ticker = st.text_input("Add ticker", "").strip().upper()
        submitted = st.form_submit_button("Add")
        if submitted and new_ticker:
            if new_ticker not in st.session_state.tickers:
                st.session_state.tickers.append(new_ticker)
                save_watchlist(st.session_state.tickers)
            st.rerun()

    for t in list(st.session_state.tickers):
        c1, c2 = st.columns([3, 1])
        c1.write(t)
        if c2.button("✕", key=f"remove_{t}"):
            st.session_state.tickers.remove(t)
            save_watchlist(st.session_state.tickers)
            st.rerun()

    st.divider()
    st.header("Lookback")
    period = st.selectbox("History window", ["3mo", "6mo", "1y", "2y"], index=1)

    st.divider()
    st.header("Thresholds")
    wr_oversold = st.slider("Williams %R oversold (≤)", -100, 0, -80)
    wr_overbought = st.slider("Williams %R overbought (≥)", -100, 0, -20)
    rsi_oversold = st.slider("RSI oversold (≤)", 0, 100, 30)
    rsi_overbought = st.slider("RSI overbought (≥)", 0, 100, 70)
    stoch_oversold = st.slider("Stochastic %K oversold (≤)", 0, 100, 20)
    stoch_overbought = st.slider("Stochastic %K overbought (≥)", 0, 100, 80)

    st.divider()
    if st.button("Refresh data"):
        fetch_data.clear()
        st.rerun()

thresholds = {
    "wr_oversold": wr_oversold,
    "wr_overbought": wr_overbought,
    "rsi_oversold": rsi_oversold,
    "rsi_overbought": rsi_overbought,
    "stoch_oversold": stoch_oversold,
    "stoch_overbought": stoch_overbought,
}

if not st.session_state.tickers:
    st.info("Add a ticker in the sidebar to get started.")
    st.stop()

rows = []
frames = {}
errors = []

for ticker in st.session_state.tickers:
    df = fetch_data(ticker, period)
    if df is None or len(df) < 20:
        errors.append(ticker)
        continue
    ind = build_indicator_frame(df)
    last = ind.iloc[-1]
    if last[["WilliamsR", "RSI", "StochK"]].isna().any():
        errors.append(ticker)
        continue
    signal, score = classify_signal(last["WilliamsR"], last["RSI"], last["StochK"], thresholds)
    rows.append({
        "Ticker": ticker,
        "Price": round(float(last["Close"]), 2),
        "Williams %R": round(float(last["WilliamsR"]), 1),
        "RSI": round(float(last["RSI"]), 1),
        "Stoch %K": round(float(last["StochK"]), 1),
        "Signal": signal,
        "_score": score,
    })
    frames[ticker] = ind

if errors:
    st.warning(f"Couldn't get enough data for: {', '.join(errors)}")

if rows:
    result_df = pd.DataFrame(rows).sort_values("_score", ascending=False).drop(columns="_score")
    active = (result_df["Signal"] != "Neutral").sum()

    st.subheader("Current readings")
    st.caption(f"{active} of {len(result_df)} tickers have an active signal.")

    only_active = st.checkbox("Show only tickers with an active signal", value=False)
    display_df = result_df[result_df["Signal"] != "Neutral"] if only_active else result_df

    def color_signal(val):
        return f"background-color: {SIGNAL_COLORS.get(val, '#8a8a8a')}; color: white"

    st.dataframe(
        display_df.style
        .map(color_signal, subset=["Signal"])
        .format({
            "Price": "{:.2f}",
            "Williams %R": "{:.1f}",
            "RSI": "{:.1f}",
            "Stoch %K": "{:.1f}",
        }),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Detail view")
    selected = st.selectbox("Ticker", list(frames.keys()))
    ind = frames[selected]

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        row_heights=[0.4, 0.2, 0.2, 0.2],
        subplot_titles=("Price", "Williams %R", "RSI", "Stochastic %K / %D"),
    )
    fig.add_trace(go.Scatter(x=ind.index, y=ind["Close"], name="Close"), row=1, col=1)

    fig.add_trace(go.Scatter(x=ind.index, y=ind["WilliamsR"], name="Williams %R"), row=2, col=1)
    fig.add_hline(y=thresholds["wr_oversold"], line_dash="dot", line_color="green", row=2, col=1)
    fig.add_hline(y=thresholds["wr_overbought"], line_dash="dot", line_color="red", row=2, col=1)

    fig.add_trace(go.Scatter(x=ind.index, y=ind["RSI"], name="RSI"), row=3, col=1)
    fig.add_hline(y=thresholds["rsi_oversold"], line_dash="dot", line_color="green", row=3, col=1)
    fig.add_hline(y=thresholds["rsi_overbought"], line_dash="dot", line_color="red", row=3, col=1)

    fig.add_trace(go.Scatter(x=ind.index, y=ind["StochK"], name="%K"), row=4, col=1)
    fig.add_trace(go.Scatter(x=ind.index, y=ind["StochD"], name="%D"), row=4, col=1)
    fig.add_hline(y=thresholds["stoch_oversold"], line_dash="dot", line_color="green", row=4, col=1)
    fig.add_hline(y=thresholds["stoch_overbought"], line_dash="dot", line_color="red", row=4, col=1)

    fig.update_layout(height=800, showlegend=False, margin=dict(t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No data available yet. Try refreshing or check your ticker symbols.")
