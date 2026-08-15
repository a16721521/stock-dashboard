import json

from backend.names import get_name, load_cache


def test_cache_miss_fetches_and_persists(tmp_path):
    p = tmp_path / "names_cache.json"
    calls = []
    name = get_name("AAPL", p, fetcher=lambda t: (calls.append(t), "Apple Inc.")[1])
    assert name == "Apple Inc."
    assert calls == ["AAPL"]
    assert json.loads(p.read_text())["AAPL"] == "Apple Inc."


def test_cache_hit_does_not_fetch(tmp_path):
    p = tmp_path / "names_cache.json"
    p.write_text(json.dumps({"MSFT": "Microsoft Corporation"}))
    calls = []
    name = get_name("MSFT", p, fetcher=lambda t: calls.append(t))
    assert name == "Microsoft Corporation"
    assert calls == []


def test_uppercases_ticker(tmp_path):
    p = tmp_path / "names_cache.json"
    name = get_name("nvda", p, fetcher=lambda t: "NVIDIA Corporation")
    assert name == "NVIDIA Corporation"
    assert json.loads(p.read_text())["NVDA"] == "NVIDIA Corporation"


def test_fetch_failure_returns_none_and_not_cached(tmp_path):
    p = tmp_path / "names_cache.json"

    def boom(t):
        raise RuntimeError("no network")

    assert get_name("ZZZZ", p, fetcher=boom) is None
    assert load_cache(p) == {}  # nothing persisted, so it can retry later


def test_empty_name_not_cached(tmp_path):
    p = tmp_path / "names_cache.json"
    assert get_name("ZZZZ", p, fetcher=lambda t: None) is None
    assert load_cache(p) == {}
