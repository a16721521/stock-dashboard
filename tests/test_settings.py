import json

import pytest
from pydantic import ValidationError

from backend.settings import (
    load_settings, save_settings, settings_health, DEFAULT_SETTINGS, SettingsModel,
)


def _valid_payload():
    return {
        "thresholds": {
            "wr_oversold": -80, "wr_overbought": -20,
            "rsi_oversold": 30, "rsi_overbought": 70,
            "stoch_oversold": 20, "stoch_overbought": 80,
        },
        "lookback": "6mo",
    }


def test_model_accepts_defaults():
    SettingsModel(**_valid_payload())  # no raise


@pytest.mark.parametrize("mutate", [
    lambda p: p["thresholds"].update(wr_oversold=-100),   # boundary -> /0 risk
    lambda p: p["thresholds"].update(rsi_oversold=0),     # boundary -> /0 risk
    lambda p: p["thresholds"].update(rsi_overbought=100), # boundary -> /0 risk
    lambda p: p["thresholds"].update(stoch_overbought=100),
    lambda p: p["thresholds"].update(rsi_oversold=80),    # reversed (os > ob)
    lambda p: p["thresholds"].update(wr_oversold=float("nan")),
    lambda p: p["thresholds"].update(wr_oversold=float("inf")),
    lambda p: p.__setitem__("lookback", "10y"),           # not allowed
    lambda p: p["thresholds"].__setitem__("bogus", 1),    # unknown key
    lambda p: p.__setitem__("extra_top", 1),              # unknown top-level key
])
def test_model_rejects_invalid(mutate):
    p = _valid_payload()
    mutate(p)
    with pytest.raises(ValidationError):
        SettingsModel(**p)


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


# ---------------------------------------------------------------------------
# P2-1: a manually edited or legacy settings file with boundary/invalid
# thresholds must never load as-is — it would crash ranking's division.
# ---------------------------------------------------------------------------

def test_load_rejects_boundary_thresholds_on_disk(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({
        "thresholds": {"wr_oversold": -100, "wr_overbought": -20,
                       "rsi_oversold": 30, "rsi_overbought": 70,
                       "stoch_oversold": 20, "stoch_overbought": 80},
        "lookback": "6mo",
    }))
    s = load_settings(p)
    assert s == DEFAULT_SETTINGS   # falls back to safe defaults, not the crash-prone value


def test_load_preserves_invalid_file_for_diagnosis(tmp_path):
    p = tmp_path / "settings.json"
    bad_text = json.dumps({"thresholds": {"wr_oversold": -100, "wr_overbought": -20,
                                          "rsi_oversold": 30, "rsi_overbought": 70,
                                          "stoch_oversold": 20, "stoch_overbought": 80},
                           "lookback": "6mo"})
    p.write_text(bad_text)
    load_settings(p)
    preserved = p.with_name("settings.invalid.json")
    assert preserved.exists()
    assert preserved.read_text() == bad_text


def test_load_rejects_corrupt_json(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not valid json")
    assert load_settings(p) == DEFAULT_SETTINGS


def test_settings_health_valid(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(_valid_payload()))
    assert settings_health(p) == {"valid": True, "reason": None}


def test_settings_health_missing_file_is_valid(tmp_path):
    # No file yet -> defaults will be used -> not an error state.
    assert settings_health(tmp_path / "settings.json")["valid"] is True


def test_settings_health_invalid_thresholds(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"thresholds": {"wr_oversold": -100, "wr_overbought": -20,
                                            "rsi_oversold": 30, "rsi_overbought": 70,
                                            "stoch_oversold": 20, "stoch_overbought": 80},
                             "lookback": "6mo"}))
    health = settings_health(p)
    assert health["valid"] is False
    assert health["reason"]


def test_settings_health_corrupt_json(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not valid json")
    assert settings_health(p)["valid"] is False
