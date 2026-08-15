"""Persisted settings: signal thresholds + lookback window."""

import json
from pathlib import Path

from backend.indicators import DEFAULT_THRESHOLDS

DEFAULT_SETTINGS = {
    "thresholds": dict(DEFAULT_THRESHOLDS),
    "lookback": "6mo",
}
LOOKBACK_CHOICES = ["3mo", "6mo", "1y", "2y"]


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
