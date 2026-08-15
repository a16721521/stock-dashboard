"""Persisted settings: signal thresholds + lookback window.

Writes go through typed Pydantic models (`SettingsModel`) so invalid or
boundary values that would crash the ranking math can never be persisted.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

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


def load_settings(path):
    path = Path(path)
    merged = {"thresholds": dict(DEFAULT_THRESHOLDS),
              "lookback": DEFAULT_SETTINGS["lookback"]}
    if path.exists():
        try:
            raw = json.loads(path.read_text())
        except Exception:
            raw = {}
        if isinstance(raw, dict):
            if isinstance(raw.get("thresholds"), dict):
                merged["thresholds"].update(raw["thresholds"])
            if raw.get("lookback") in LOOKBACK_CHOICES:
                merged["lookback"] = raw["lookback"]
    return merged


def save_settings(path, data):
    Path(path).write_text(json.dumps(data, indent=2))
