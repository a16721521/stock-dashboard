"""Persisted settings: signal thresholds + lookback window.

Writes go through typed Pydantic models (`SettingsModel`) so invalid or
boundary values that would crash the ranking math can never be persisted.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from backend.indicators import DEFAULT_THRESHOLDS

DEFAULT_SETTINGS = {
    "thresholds": dict(DEFAULT_THRESHOLDS),
    "lookback": "6mo",
}
LOOKBACK_CHOICES = ["3mo", "6mo", "1y", "2y"]


class ThresholdsModel(BaseModel):
    """Oscillator thresholds with strict ordering so normalized-distance
    denominators are never zero and oversold < overbought always holds."""

    model_config = ConfigDict(extra="forbid")

    wr_oversold: float
    wr_overbought: float
    rsi_oversold: float
    rsi_overbought: float
    stoch_oversold: float
    stoch_overbought: float

    @model_validator(mode="after")
    def _ordered_and_bounded(self):
        if not (-100 < self.wr_oversold < self.wr_overbought < 0):
            raise ValueError("require -100 < wr_oversold < wr_overbought < 0")
        if not (0 < self.rsi_oversold < self.rsi_overbought < 100):
            raise ValueError("require 0 < rsi_oversold < rsi_overbought < 100")
        if not (0 < self.stoch_oversold < self.stoch_overbought < 100):
            raise ValueError("require 0 < stoch_oversold < stoch_overbought < 100")
        return self


class SettingsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thresholds: ThresholdsModel
    lookback: Literal["3mo", "6mo", "1y", "2y"]


def _load_raw_merged(path):
    """Read + merge settings.json over defaults, WITHOUT validating.
    Returns None if the file exists but is unparseable (corrupt/not an
    object) — the caller decides how to handle that."""
    path = Path(path)
    if not path.exists():
        return {"thresholds": dict(DEFAULT_THRESHOLDS), "lookback": DEFAULT_SETTINGS["lookback"]}
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    thresholds = dict(DEFAULT_THRESHOLDS)
    if isinstance(raw.get("thresholds"), dict):
        thresholds.update(raw["thresholds"])
    lookback = raw.get("lookback", DEFAULT_SETTINGS["lookback"])
    return {"thresholds": thresholds, "lookback": lookback}


def _preserve_invalid(path):
    """Copy an invalid settings.json to settings.invalid.json for diagnosis
    before it gets replaced by defaults, per P2-1: never silently discard a
    manually edited file without a trace."""
    path = Path(path)
    if not path.exists():
        return
    try:
        dest = path.with_name(path.stem + ".invalid" + path.suffix)
        dest.write_text(path.read_text())
    except Exception:
        pass  # best-effort; must never block falling back to safe defaults


def load_settings(path):
    """Always returns a SettingsModel-valid dict. A missing file loads
    defaults; a corrupt or out-of-range file (e.g. hand-edited or from an
    older schema) is preserved for diagnosis and defaults are returned instead
    — malformed persisted state must never reach ranking (P2-1)."""
    merged = _load_raw_merged(path)
    if merged is None:
        return SettingsModel(**DEFAULT_SETTINGS).model_dump()
    try:
        return SettingsModel(**merged).model_dump()
    except ValidationError:
        _preserve_invalid(path)
        return SettingsModel(**DEFAULT_SETTINGS).model_dump()


def settings_health(path):
    """Report whether the on-disk settings file (if any) is currently valid,
    without mutating anything — used to surface a warning in /api/data-status
    even when load_settings() has already silently fallen back to defaults."""
    merged = _load_raw_merged(Path(path))
    if merged is None:
        return {"valid": False, "reason": "corrupt_or_unreadable"}
    try:
        SettingsModel(**merged)
        return {"valid": True, "reason": None}
    except ValidationError:
        return {"valid": False, "reason": "validation_error"}


def save_settings(path, data):
    Path(path).write_text(json.dumps(data, indent=2))
