"""FastAPI app: JSON API + static frontend. Fetchers are injectable for tests."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import pandas as pd

from backend import data as data_mod
from backend.indicators import build_indicator_frame, classify_signal
from backend.ranking import rank_rows
from backend.scan import run_scan, save_cache, load_cache
from backend.settings import load_settings, save_settings
from backend.universe import load_universe
from backend.watchlist import load_watchlist, save_watchlist

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


def _json_series(s):
    """Round a numeric series and convert NaN to None for JSON compliance.

    (pandas coerces `None` back to NaN inside a float series, so we can't use
    Series.where — build the list explicitly.)"""
    s = s.round(2)
    return [None if pd.isna(v) else float(v) for v in s]


def create_app(data_dir, ticker_fetcher=None, batch_fetcher=None):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    watchlist_path = data_dir / "watchlist.json"
    settings_path = data_dir / "settings.json"
    cache_path = data_dir / "scan_cache.json"

    if ticker_fetcher is None:
        ticker_fetcher = data_mod.fetch_history
    if batch_fetcher is None:
        batch_fetcher = data_mod.fetch_batch

    app = FastAPI(title="Indicator Dashboard")
    app.state.scanning = False

    # ---- Watchlist ----
    @app.get("/api/watchlist")
    def get_watchlist():
        return load_watchlist(watchlist_path)

    @app.put("/api/watchlist")
    def put_watchlist(payload: dict):
        save_watchlist(watchlist_path, payload)
        return {"ok": True}

    # ---- Settings ----
    @app.get("/api/settings")
    def get_settings():
        return load_settings(settings_path)

    @app.put("/api/settings")
    def put_settings(payload: dict):
        save_settings(settings_path, payload)
        return {"ok": True}

    # ---- Ticker detail ----
    @app.get("/api/ticker/{symbol}")
    def get_ticker(symbol: str):
        settings = load_settings(settings_path)
        df = ticker_fetcher(symbol.upper(), settings["lookback"])
        if df is None or len(df) < 20:
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")
        ind = build_indicator_frame(df)
        last = ind.iloc[-1]
        if last[["WilliamsR", "RSI", "StochK"]].isna().any():
            raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")
        signal, score = classify_signal(
            last["WilliamsR"], last["RSI"], last["StochK"], settings["thresholds"])
        return {
            "ticker": symbol.upper(),
            "series": {
                "dates": [d.strftime("%Y-%m-%d") for d in ind.index],
                "close": _json_series(ind["Close"]),
                "wr": _json_series(ind["WilliamsR"]),
                "rsi": _json_series(ind["RSI"]),
                "stochK": _json_series(ind["StochK"]),
                "stochD": _json_series(ind["StochD"]),
            },
            "latest": {
                "price": round(float(last["Close"]), 2),
                "wr": round(float(last["WilliamsR"]), 1),
                "rsi": round(float(last["RSI"]), 1),
                "stochK": round(float(last["StochK"]), 1),
                "signal": signal,
                "score": score,
            },
            "thresholds": settings["thresholds"],
        }

    # ---- Marketwide scan ----
    def _do_scan():
        settings = load_settings(settings_path)
        universe = load_universe()
        rows = run_scan(universe, settings["lookback"], batch_fetcher)
        save_cache(cache_path, rows, "sp500+nasdaq100")

    @app.post("/api/scan/run")
    def scan_run():
        app.state.scanning = True
        try:
            _do_scan()
        finally:
            app.state.scanning = False
        return {"ok": True}

    @app.get("/api/scan")
    def scan_get(tab: str = "top_buy"):
        cache = load_cache(cache_path)
        settings = load_settings(settings_path)
        if cache is None:
            return {"scanned_at": None, "scanning": app.state.scanning, "rows": []}
        ranked = rank_rows(cache["rows"], settings["thresholds"], tab)
        return {"scanned_at": cache["scanned_at"], "scanning": app.state.scanning,
                "tab": tab, "rows": ranked}

    # ---- Static frontend ----
    if FRONTEND_DIR.exists():
        @app.get("/")
        def index():
            return FileResponse(FRONTEND_DIR / "index.html")
        app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")

    return app


# Real app for uvicorn: data files live in the project root.
app = create_app(data_dir=Path(__file__).parent.parent)
