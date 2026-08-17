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
    run_scan, build_cache_payload, commit_scan, save_attempt, load_cache,
    needs_scan, calculation_hash, ranking_hash, universe_hash, settings_hash,
)
from backend.scheduler import start_background_timer
from backend.settings import SettingsModel, load_settings, save_settings, settings_health
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
    attempt_path = data_dir / "scan_last_attempt.json"
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

    def _current_config():
        """The configuration a freshly-run scan would be computed under right
        now — used to detect when the committed cache is out of date."""
        settings = load_settings(settings_path)
        universe = load_universe()
        return {
            "settings": settings,
            "universe": universe,
            "calculation_hash": calculation_hash(settings["lookback"]),
            "ranking_hash": ranking_hash(settings["thresholds"]),
            "universe_hash": universe_hash(universe),
        }

    def _is_compatible(cache, cfg):
        if cache is None:
            return False
        return (cache.get("calculation_hash") == cfg["calculation_hash"]
                and cache.get("universe_hash") == cfg["universe_hash"])

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
        bar_date = ind.index[-1].strftime("%Y-%m-%d")
        return {
            "ticker": symbol.upper(),
            "name": names_mod.get_name(symbol.upper(), names_path, name_fetcher),
            "bar_date": bar_date,
            "bar_status": market_calendar.bar_status(bar_date),
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
        cfg = _current_config()
        started = datetime.now(timezone.utc).isoformat()
        result = run_scan(load_universe(), cfg["settings"]["lookback"], batch_fetcher)
        payload = build_cache_payload(
            result,
            lookback=cfg["settings"]["lookback"],
            universe_id="sp500+nasdaq100",
            universe_hash=cfg["universe_hash"],
            calculation_hash=cfg["calculation_hash"],
            ranking_hash=cfg["ranking_hash"],
            expected_session_date=market_calendar.expected_session_date(),
            started_at=started,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        outcome = commit_scan(cache_path, payload)
        save_attempt(attempt_path, payload, outcome)
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
        cfg = _current_config()
        if cache is None:
            return {"scanned_at": None, "scanning": app.state.scanning,
                    "status": None, "configuration_compatible": False, "rows": []}
        ranked = rank_rows(cache["rows"], cfg["settings"]["thresholds"], tab)
        return {
            "scanned_at": cache.get("completed_at") or cache.get("scanned_at"),
            "scanning": app.state.scanning,
            "tab": tab,
            "status": cache.get("status"),
            "latest_bar_date": cache.get("latest_bar_date"),
            "expected_session_date": cache.get("expected_session_date"),
            "coverage": cache.get("coverage"),
            "date_coverage": cache.get("date_coverage"),
            "configuration_compatible": _is_compatible(cache, cfg),
            "rows": ranked,
        }

    def _staleness_warnings(cache, bar_status_value):
        warnings = []
        if cache is None:
            warnings.append("No scan has run yet.")
            return warnings
        if bar_status_value == "stale":
            warnings.append("Latest committed data is stale (older than the last closed session).")
        elif bar_status_value == "provisional":
            warnings.append("Latest bar is provisional (current session not yet closed).")
        elif bar_status_value == "unknown":
            warnings.append("Data freshness unknown.")
        # Flag genuinely OLDER-than-expected bars (the P1-2 masking concern:
        # some symbols behind while others are current). Bars that are newer
        # than the last closed session are provisional/intraday, not stale —
        # that's already surfaced above via bar_status, so don't double-warn.
        date_cov = cache.get("date_coverage") or {}
        older = date_cov.get("older_date_count", 0)
        if older:
            total_valid = cache.get("coverage", {}).get("valid", "?")
            warnings.append(
                f"{older} of {total_valid} scanned symbols have an older bar than the "
                f"expected session date ({date_cov.get('expected_date', '—')}); "
                f"freshness is uneven across the universe.")
        cov = cache.get("coverage") or {}
        if cov.get("missing"):
            warnings.append(f"Partial fetch coverage: {cov['missing']} of "
                            f"{cov.get('requested')} symbols missing.")
        if cache.get("status") == "partial":
            warnings.append("Most recent committed scan is partial row coverage.")
        return warnings

    def _attempt_warning(last_success, last_attempt):
        if not last_attempt or last_attempt.get("commit_outcome", {}).get("committed"):
            return None
        if not last_attempt.get("completed_at"):
            return None
        if last_success and last_success.get("completed_at") and \
           last_attempt["completed_at"] <= last_success["completed_at"]:
            return None   # the attempt IS the current success; nothing to flag
        reason = last_attempt.get("commit_outcome", {}).get("reason", "unknown")
        if last_success:
            return (f"Most recent refresh attempt failed ({reason}); "
                    f"showing last good data through {last_success.get('bar_date', '—')}.")
        return f"Most recent scan attempt failed ({reason}); no data available yet."

    @app.get("/api/data-status")
    def data_status():
        cache = load_cache(cache_path)
        attempt = load_cache(attempt_path)
        cfg = _current_config()
        health = settings_health(settings_path)

        latest_bar = cache.get("latest_bar_date") if cache else None
        bar_status_value = market_calendar.bar_status(latest_bar)
        compatible = _is_compatible(cache, cfg)

        last_success = ({"completed_at": cache.get("completed_at"),
                         "bar_date": cache.get("latest_bar_date"),
                         "status": cache.get("status")} if cache else None)
        last_attempt = ({"completed_at": attempt.get("completed_at"),
                         "status": attempt.get("status"),
                         "commit_outcome": attempt.get("commit_outcome"),
                         "errors": attempt.get("errors")} if attempt else None)

        warnings = _staleness_warnings(cache, bar_status_value)
        if not compatible and cache is not None:
            warnings.append("Displayed data was scanned under a different configuration "
                            "(lookback, algorithm, or universe changed) — a rescan is pending.")
        if not health["valid"]:
            warnings.append("Saved settings file was invalid; using defaults. "
                            "The invalid file was preserved for review.")
        attempt_warning = _attempt_warning(last_success, last_attempt)
        if attempt_warning:
            warnings.append(attempt_warning)

        return {
            "expected_session_date": market_calendar.expected_session_date(),
            "latest_bar_date": latest_bar,
            "bar_status": bar_status_value,
            "cache_status": cache.get("status") if cache else None,
            "coverage": cache.get("coverage") if cache else None,
            "date_coverage": cache.get("date_coverage") if cache else None,
            "scanning": app.state.scanning,
            "algorithm_version": cache.get("algorithm_version") if cache else None,
            "calculation_hash": cfg["calculation_hash"],
            "settings_hash": settings_hash(cfg["settings"]),
            "configuration_compatible": compatible,
            "settings_valid": health["valid"],
            "last_success": last_success,
            "last_attempt": last_attempt,
            "warnings": warnings,
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

    def _needs_scan_now():
        cfg = _current_config()
        return needs_scan(
            load_cache(cache_path),
            expected_session_date=market_calendar.expected_session_date(),
            calculation_hash_value=cfg["calculation_hash"],
            universe_hash_value=cfg["universe_hash"],
        )

    def _startup_tasks():
        if _needs_scan_now():
            threading.Thread(target=_wrapped_scan, daemon=True).start()
        start_background_timer(
            run_scan_callback=_wrapped_scan,
            needs_scan_fn=_needs_scan_now,
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
