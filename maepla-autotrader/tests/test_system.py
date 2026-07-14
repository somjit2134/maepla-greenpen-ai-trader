import pytest
import numpy as np
import pandas as pd

from src.config import load, get
from src.market import (detect_structure, detect_sr, analyze_grid,
                        analyze_ath, analyze_frame, analyze_pa, run_analysis)
from src.risk import RiskManager
from src.connector import SimConnector
from src.database import Database
from src.backtest import run_backtest


@pytest.fixture
def cfg():
    load()
    return get()


@pytest.fixture
def sample_df():
    np.random.seed(42)
    n = 100
    prices = 4000 + np.cumsum(np.random.randn(n) * 5)
    return pd.DataFrame({
        "time": pd.date_range("2026-07-01", periods=n, freq="h"),
        "open": prices + np.random.randn(n) * 2,
        "high": prices + np.abs(np.random.randn(n)) * 8 + 3,
        "low": prices - np.abs(np.random.randn(n)) * 8 - 3,
        "close": prices,
        "tick_volume": np.random.randint(100, 5000, n),
        "spread": np.random.randint(10, 50, n),
        "real_volume": np.random.randint(1000, 50000, n),
    })


@pytest.fixture
def bullish_df():
    np.random.seed(42)
    n = 100
    prices = 4000 + np.linspace(0, 200, n) + np.random.randn(n) * 3
    return pd.DataFrame({
        "time": pd.date_range("2026-07-01", periods=n, freq="h"),
        "open": prices + np.random.randn(n) * 2,
        "high": prices + np.abs(np.random.randn(n)) * 6 + 4,
        "low": prices - np.abs(np.random.randn(n)) * 6 - 4,
        "close": prices,
        "tick_volume": np.random.randint(100, 5000, n),
        "spread": np.random.randint(10, 50, n),
        "real_volume": np.random.randint(1000, 50000, n),
    })


# --- Market Structure ---

def test_structure_bearish(sample_df):
    r = detect_structure(sample_df)
    assert r.condition in ("BULLISH", "BEARISH", "RANGE")
    assert r.preference in ("BUY", "SELL", "WAIT")


def test_structure_bullish(bullish_df):
    r = detect_structure(bullish_df)
    assert r.condition == "BULLISH"


def test_structure_insufficient_data():
    r = detect_structure(pd.DataFrame())
    assert r.detail == "insufficient data"


# --- S/R ---

def test_sr_detection(sample_df):
    r = detect_sr(sample_df)
    assert len(r.supports) + len(r.resistances) > 0


# --- Grid ---

def test_grid_analysis():
    r = analyze_grid(4075)
    assert r.nearest is not None
    assert r.score >= 0
    assert len(r.levels) > 0


def test_grid_at_level():
    r = analyze_grid(4100)
    assert r.nearest == 4100
    assert r.score == 2


def test_grid_near_level():
    r = analyze_grid(4108)
    assert r.score >= 1


# --- ATH ---

def test_ath():
    r = analyze_ath(4073)
    assert r.distance_pct > 0
    assert not r.is_near
    assert r.score == 1


def test_ath_near():
    r = analyze_ath(5500)
    assert r.is_near
    assert r.score == 0


# --- Frame ---

def test_frame():
    r = analyze_frame(None, price=4073)
    assert r.position in ("BEGINNING", "MIDDLE", "END")


# --- PA ---

def test_pa_analysis(sample_df):
    r = analyze_pa(sample_df)
    assert r.overall in ("BULLISH", "BEARISH", "NEUTRAL")
    assert r.score >= 0


# --- Risk ---

def test_position_size():
    rm = RiskManager()
    lots = rm.position_size(10000, 4075, 4060, 1.0)
    assert 0.01 <= lots <= 10.0


def test_rr():
    rm = RiskManager()
    assert rm.rr(4075, 4060, 4100) > 1.0


def test_risk_check():
    rm = RiskManager()
    c = rm.check(10000, 4075, 4060, 4100, "BUY", 1.0)
    assert "passed" in c
    assert "lot_size" in c


def test_risk_limits():
    rm = RiskManager()
    ok, msg = rm.can_open_trade(0, {"net_pnl": 0})
    assert ok


# --- Simulated Connector ---

def test_sim_connect():
    c = SimConnector()
    assert c.connect()
    assert c.connected
    bid, ask, spread = c.tick()
    assert bid > 0 and ask > 0
    data = c.rates("H1", 10)
    assert not data.empty
    assert len(data) == 10
    c.disconnect()


# --- Full Analysis ---

def test_full_analysis():
    c = SimConnector()
    c.connect()
    data = c.all_rates(count=200)
    bid, ask, spread = c.tick()
    r = run_analysis(data, bid, ask, spread)
    assert r.price > 0
    assert r.monthly in ("BULLISH", "BEARISH", "RANGE")
    assert r.decision in ("BUY", "SELL", "WAIT")
    assert 0 <= r.total_score <= 10
    assert r.grade != ""
    c.disconnect()


# --- Database ---

def test_db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    aid = db.save_analysis({"time": "2026-01-01", "price": 4000, "decision": "SELL",
                            "score": 8, "monthly": "BEARISH", "weekly": "BEARISH",
                            "daily_zone": "S:4000 R:4050", "h4": "BEARISH", "h1": "BEARISH",
                            "supports": [], "resistances": [],
                            "grid_score": 2, "ath_pct": 27.0, "thousand_pt": "MIDDLE",
                            "pa_bullish": False, "pa_bearish": True,
                            "score_breakdown": {}, "trade_plan": {}})
    assert aid > 0

    sid = db.save_signal({"analysis_id": aid, "time": "2026-01-01", "price": 4000,
                          "direction": "SELL", "score": 8, "grade": "B", "source": "TEST"})
    assert sid > 0

    oid = db.save_order({"signal_id": sid, "ticket": 12345, "time": "2026-01-01",
                         "symbol": "XAUUSD", "direction": "SELL", "volume": 0.1,
                         "entry_price": 4000, "stop_loss": 4010, "take_profit": 3980,
                         "risk_pct": 1.0, "rr": 2.0, "status": "OPEN"})
    assert oid > 0

    signals = db.get_signals(5)
    assert len(signals) > 0

    orders = db.get_orders("OPEN")
    assert len(orders) > 0

    db.close_order(oid, 3985, 15.0, "take_profit")
    orders = db.get_orders("CLOSED")
    assert len(orders) > 0

    db.close()


# --- Backtest ---

def test_backtest():
    c = SimConnector()
    c.connect()
    data = c.all_rates(count=100)
    r = run_backtest(data, initial_balance=10000, rr_target=2.0, sl_atr_mult=1.5)
    assert r.total_trades >= 0
    assert r.wins + r.losses == r.total_trades
    c.disconnect()


# --- Config ---

def test_config():
    cfg = get()
    assert cfg.symbol.name == "XAUUSD"
    assert cfg.symbol.at == 5603.0
    assert cfg.risk.min_rr == 2.0
    assert cfg.trading.execute_score_threshold == 9
    assert cfg.trading.alert_score_threshold == 7
