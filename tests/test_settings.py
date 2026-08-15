import json

from backend.settings import load_settings, save_settings, DEFAULT_SETTINGS


def test_missing_file_returns_defaults(tmp_path):
    s = load_settings(tmp_path / "settings.json")
    assert s == DEFAULT_SETTINGS
    assert s["thresholds"]["rsi_oversold"] == 30
    assert s["lookback"] == "6mo"


def test_partial_file_is_merged_over_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"lookback": "1y"}))
    s = load_settings(p)
    assert s["lookback"] == "1y"
    assert s["thresholds"]["rsi_oversold"] == 30  # default preserved


def test_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    s = load_settings(p)
    s["lookback"] = "2y"
    save_settings(p, s)
    assert load_settings(p)["lookback"] == "2y"
