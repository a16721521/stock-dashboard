"""FastAPI app: JSON API + static frontend. Fetchers are injectable for tests."""

import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import pandas as pd

from backend import data as data_mod
from backend import market_calendar
from backend import names as names_mod
from backend.indicators import build_indicator_frame, classify_state
from backend.ranking import rank_rows
from backend.scan import (
    run_scan, build_cache_payload, commit_scan, load_cache,
    settings_hash, universe_hash,
)
from backend.settings import SettingsModel, load_settings, save_settings
from backend.universe import load_universe
from backend.watchlist import load_watchlist, save_watchlist

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


def _json_series(s):
    """Round a numeric series and convert NaN to None for JSON compliance.

    (pandas coerces `None` back to NaN inside a float series, so we can't use
    Series.where — build the list explicitly.)"""
    s = s.round(2)
    return [None if pd.isna(v) else float(v) for v in s]


def create_app(data_dir, ticker_fetcher=None, batch_fetcher=None, name_fetcher=None):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    watchlist_path = data_dir / "watchlist.json"
    settings_path = data_dir / "settings.json"
    cache_path = data_dir / "scan_cache.json"
    names_path = data_dir / "names_cache.json"

    if ticker_fetcher is None:
        ticker_fetcher = data_mod.fetch_history
    if batch_fetcher is None:
        batch_fetcher = data_mod.fetch_batch
    if name_fetcher is None:
        name_fetcher = names_mod._default_fetcher

    @asynccontextmanager
    async def lifespan(_app):
        _startup_tasks()   # defined below; bound by the time this runs
        yield

    app = FastAPI(title="Indicator Dashboard", lifespan=lifespan)
    app.state.scanning = False
    app.state.scan_lock = threading.Lock()

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
    def put_settings(payload: SettingsModel):
        save_settings(settings_path, payload.model_dump())
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
        cls = classify_state(
            float(last["WilliamsR"]), float(last["RSI"]), settings["thresholds"])
        return {
            "ticker": symbol.upper(),
            "name": names_mod.get_name(symbol.upper(), names_path, name_fetcher),
            "bar_date": ind.index[-1].strftime("%Y-%m-%d"),
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
                "state": cls["state"],
                "score": cls["score"],
                "research_status": cls["research_status"],
            },
            "thresholds": settings["thresholds"],
        }

    # ---- Marketwide scan ----
    def _do_scan():
        settings = load_settings(settings_path)
        universe = load_universe()
        started = datetime.now(timezone.utc).isoformat()
        result = run_scan(universe, settings["lookback"], batch_fetcher)
        payload = build_cache_payload(
            result,
            lookback=settings["lookback"],
            universe_id="sp500+nasdaq100",
            universe_hash=universe_hash(universe),
            settings_hash=settings_hash(settings),
            expected_session_date=market_calendar.expected_session_date(),
            started_at=started,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        outcome = commit_scan(cache_path, payload)
        app.state.last_scan_outcome = outcome
        return outcome

    @app.post("/api/scan/run")
    def scan_run():
        outcome = _wrapped_scan()
        if outcome.get("reason") == "already_running":
            raise HTTPException(status_code=409, detail="A scan is already running")
        return outcome

    @app.get("/api/scan")
    def scan_get(tab: str = "most_oversold"):
        cache = load_cache(cache_path)
        settings = load_settings(settings_path)
        if cache is None:
            return {"scanned_at": None, "scanning": app.state.scanning,
                    "status": None, "rows": []}
        ranked = rank_rows(cache["rows"], settings["thresholds"], tab)
        return {
            "scanned_at": cache.get("completed_at") or cache.get("scanned_at"),
            "scanning": app.state.scanning,
            "tab": tab,
            "status": cache.get("status"),
            "latest_bar_date": cache.get("latest_bar_date"),
            "expected_session_date": cache.get("expected_session_date"),
            "coverage": cache.get("coverage"),
            "rows": ranked,
        }

    def _data_warnings(cache, bar_status):
        warnings = []
        if cache is None:
            warnings.append("No scan has run yet.")
            return warnings
        if bar_status == "stale":
            warnings.append("Market data is stale (older than the last closed session).")
        elif bar_status == "provisional":
            warnings.append("Latest bar is provisional (current session not yet closed).")
        elif bar_status == "unknown":
            warnings.append("Data freshness unknown.")
        cov = cache.get("coverage") or {}
        if cov.get("missing"):
            warnings.append(f"Partial coverage: {cov['missing']} of "
                            f"{cov.get('requested')} symbols missing.")
        if cache.get("status") == "failed":
            warnings.append("Most recent scan failed; showing last known-good data.")
        return warnings

    @app.get("/api/data-status")
    def data_status():
        cache = load_cache(cache_path)
        settings = load_settings(settings_path)
        latest_bar = cache.get("latest_bar_date") if cache else None
        status = market_calendar.bar_status(latest_bar)
        return {
            "expected_session_date": market_calendar.expected_session_date(),
            "latest_bar_date": latest_bar,
            "bar_status": status,
            "cache_status": cache.get("status") if cache else None,
            "coverage": cache.get("coverage") if cache else None,
            "scanning": app.state.scanning,
            "algorithm_version": cache.get("algorithm_version") if cache else None,
            "settings_hash": settings_hash(settings),
            "warnings": _data_warnings(cache, status),
        }

    def _wrapped_scan():
        # Non-blocking: if a scan is already running, skip rather than pile up.
        if not app.state.scan_lock.acquire(blocking=False):
            return {"committed": False, "reason": "already_running"}
        app.state.scanning = True
        try:
            return _do_scan()
        finally:
            app.state.scanning = False
            app.state.scan_lock.release()

    def _startup_tasks():
        from backend.scheduler import is_stale, start_background_timer
        cache = load_cache(cache_path)
        scanned_at = (cache.get("completed_at") or cache.get("scanned_at")) if cache else None
        if is_stale(scanned_at):
            threading.Thread(target=_wrapped_scan, daemon=True).start()
        start_background_timer(
            run_scan_callback=_wrapped_scan,
            get_scanned_at=lambda: (load_cache(cache_path) or {}).get("scanned_at"),
        )

    # ---- Static frontend ----
    if FRONTEND_DIR.exists():
        @app.get("/")
        def index():
            return FileResponse(FRONTEND_DIR / "index.html")
        app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")

    return app


# Real app for uvicorn: data files live in the project root.
app = create_app(data_dir=Path(__file__).parent.parent)
