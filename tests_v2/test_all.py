"""
Tests for MT5 Autonomous Trading System
=========================================
Tests all engines with simulated data (no live MT5 required).
"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import load_config, get_config
from frame_engine import FrameAnalyzer, FrameResult
from cycle_engine import CycleAnalyzer, CycleResult
from trend_engine import TrendAnalyzer, TrendResult
from price_action import PriceActionDetector, PAResult
from signal_engine import SignalEngine, SignalResult
from risk_manager import RiskManager, RiskCheck
from journal import Journal
from backtest import BacktestEngine, BacktestResult


def generate_ohlcv(n=200, trend="up", base_price=2000.0):
    """Generate simulated OHLCV data."""
    np.random.seed(42)
    times = pd.date_range(end=pd.Timestamp.now(), periods=n, freq="1h")
    noise = np.random.randn(n) * 5

    if trend == "up":
        prices = base_price + np.linspace(0, 100, n) + noise.cumsum()
    elif trend == "down":
        prices = base_price + np.linspace(0, -100, n) + noise.cumsum()
    else:
        prices = base_price + noise.cumsum() * 0.5

    df = pd.DataFrame({
        "time": times,
        "open": prices + np.random.randn(n) * 2,
        "high": prices + np.abs(np.random.randn(n)) * 5 + 3,
        "low": prices - np.abs(np.random.randn(n)) * 5 - 3,
        "close": prices,
        "tick_volume": np.random.randint(100, 5000, n),
    })
    return df


def generate_multi_tf(trend="up"):
    """Generate multi-timeframe data."""
    return {
        "D1": generate_ohlcv(100, trend, 2000),
        "H4": generate_ohlcv(200, trend, 2000),
        "H1": generate_ohlcv(300, trend, 2000),
        "M15": generate_ohlcv(400, trend, 2000),
    }


def test_config():
    print("=== Testing Config ===")
    cfg = load_config()
    assert cfg.mt5.path, "MT5 path not set"
    assert cfg.symbol.name == "XAUUSD", "Symbol should be XAUUSD"
    assert cfg.risk.risk_per_trade_percent == 1.0, "Risk should be 1%"
    assert cfg.risk.min_rr == 2.0, "Min RR should be 2"
    print("  [PASS] Config loaded correctly")
    print()


def test_frame_engine():
    print("=== Testing Frame Engine ===")
    analyzer = FrameAnalyzer()

    data = generate_multi_tf("up")
    price = 2050.0

    result = analyzer.analyze(data, price)

    assert isinstance(result, FrameResult), "Should return FrameResult"
    assert result.ath.ath > 0, "ATH should be > 0"
    assert result.cycle.total_range > 0, "Cycle range should be > 0"
    assert result.cycle.position in ("BEGINNING", "MIDDLE", "END"), "Invalid cycle position"
    assert result.overall_frame in ("RANGE", "TREND", "BREAKOUT_UP", "BREAKOUT_DOWN",
                                     "ATH_BREAK", "ATH_REJECT"), "Invalid frame"
    assert len(result.important_zones) > 0, "Should have important zones"

    print(f"  ATH: ${result.ath.ath:.2f}, Dist: {result.ath.distance_percent:.1f}%")
    print(f"  Cycle: {result.cycle.position} ({result.cycle.progress_percent:.0f}%)")
    print(f"  Sideway: {result.sideway.in_range}")
    print(f"  Frame: {result.overall_frame}")
    print(f"  Zones: {len(result.important_zones)}")
    print("  [PASS] Frame Engine working")
    print()


def test_cycle_engine():
    print("=== Testing Cycle Engine ===")
    analyzer = CycleAnalyzer()

    data = generate_multi_tf("up")
    price = 2050.0

    result = analyzer.analyze(data, price)

    assert isinstance(result, CycleResult), "Should return CycleResult"
    assert result.total_distance > 0, "Total distance should be > 0"
    assert 0 <= result.progress_percent <= 100, "Progress should be 0-100"
    assert result.position in ("EARLY", "MIDDLE", "LATE"), "Invalid position"
    assert 0 <= result.rsi_value <= 100, "RSI should be 0-100"

    print(f"  Position: {result.position}")
    print(f"  Progress: {result.progress_percent:.0f}%")
    print(f"  Remaining: {result.remaining_potential:.0f} pts")
    print(f"  RSI: {result.rsi_value:.1f}")
    print(f"  Exhaustion: {result.exhaustion_risk}")
    print("  [PASS] Cycle Engine working")
    print()


def test_trend_engine():
    print("=== Testing Trend Engine ===")
    analyzer = TrendAnalyzer()

    data = generate_multi_tf("up")
    result = analyzer.analyze(data)

    assert isinstance(result, TrendResult), "Should return TrendResult"
    assert result.alignment_score >= 0, "Alignment score should be >= 0"
    assert result.direction in ("BUY", "SELL", "WAIT"), "Invalid direction"

    print(f"  D1: {result.d1.bias}")
    print(f"  H4: {result.h4.bias}")
    print(f"  H1: {result.h1.bias}")
    print(f"  M15: {result.m15.bias}")
    print(f"  Alignment: {result.alignment_score}")
    print(f"  Direction: {result.direction}")
    print(f"  Tradeable: {result.is_tradeable}")
    print("  [PASS] Trend Engine working")
    print()


def test_price_action():
    print("=== Testing Price Action ===")
    detector = PriceActionDetector()

    df = generate_ohlcv(100, "up")
    result = detector.detect(df)

    assert isinstance(result, PAResult), "Should return PAResult"
    assert result.overall in ("BULLISH", "BEARISH", "NEUTRAL"), "Invalid overall"
    assert result.signal_grade in ("A", "B", "C", "NO_TRADE"), "Invalid grade"

    print(f"  Patterns: {len(result.patterns)}")
    print(f"  Overall: {result.overall}")
    print(f"  Grade: {result.signal_grade}")
    print(f"  Bullish: {result.bullish_count}, Bearish: {result.bearish_count}")
    for p in result.patterns[:3]:
        print(f"    - {p.name}: {p.direction} (strength {p.strength})")
    print("  [PASS] Price Action working")
    print()


def test_signal_engine():
    print("=== Testing Signal Engine ===")
    engine = SignalEngine()

    data = generate_multi_tf("up")
    bid, ask = 2000.0, 2000.5

    result = engine.analyze(data, bid, ask)

    assert isinstance(result, SignalResult), "Should return SignalResult"
    assert result.direction in ("BUY", "SELL", "WAIT"), "Invalid direction"
    assert result.signal_grade in ("A+", "A", "B+", "B", "NO_TRADE"), "Invalid grade"
    assert result.confidence_score >= 0, "Score should be >= 0"

    print(f"  Direction: {result.direction}")
    print(f"  Grade: {result.signal_grade}")
    print(f"  Score: {result.confidence_score}/10")
    print(f"  RR: {result.risk_reward}:1")
    if result.direction != "WAIT":
        print(f"  Entry: ${result.entry_price:.2f}")
        print(f"  SL: ${result.stop_loss:.2f}")
        print(f"  TP1: ${result.take_profit_1:.2f}")
    print(f"  Reasons: {', '.join(result.reasons[:3])}")
    print("  [PASS] Signal Engine working")
    print()


def test_risk_manager():
    print("=== Testing Risk Manager ===")
    mgr = RiskManager()

    lot = mgr.calculate_position_size(10000, 2000, 1990)
    assert lot > 0, "Lot size should be > 0"
    print(f"  Position size: {lot:.2f} lots")

    rr = mgr.calculate_rr(2000, 1990, 2020)
    assert rr == 2.0, f"RR should be 2.0, got {rr}"
    print(f"  RR: {rr}:1")

    check = mgr.validate_trade("BUY", 2000, 1990, 2020, 10000, open_positions=0)
    assert check.passed, f"Should pass: {check.warnings}"
    print(f"  Risk check: PASSED, lots={check.position_size:.2f}")

    check = mgr.validate_trade("BUY", 2000, 1990, 1995, 10000)
    assert not check.passed, "Should fail: RR too low"
    print(f"  Low RR check: correctly rejected")

    check = mgr.validate_trade("BUY", 2000, 2010, 2020, 10000)
    assert not check.passed, "Should fail: invalid levels"
    print(f"  Invalid levels check: correctly rejected")

    print("  [PASS] Risk Manager working")
    print()


def test_journal():
    print("=== Testing Journal ===")
    import tempfile
    tmp = tempfile.mktemp(suffix=".db")
    j = Journal(tmp)

    trade_id = j.log_trade({
        "ticket": 12345,
        "direction": "BUY",
        "entry_price": 2000.0,
        "stop_loss": 1990.0,
        "take_profit_1": 2020.0,
        "lot_size": 0.1,
        "risk_reward": 2.0,
        "signal_grade": "A",
        "score": 8.0,
    })
    assert trade_id > 0, "Trade ID should be > 0"

    j.close_trade(12345, 2020.0, 200.0, profit_pips=200, exit_reason="TP")
    trades = j.get_closed_trades()
    assert len(trades) == 1, "Should have 1 closed trade"
    assert trades[0]["profit"] == 200.0

    wr = j.win_rate()
    assert wr == 100.0, f"Win rate should be 100%, got {wr}%"
    print(f"  Win rate: {wr}%")

    pf = j.profit_factor()
    print(f"  Profit factor: {pf}")

    report = j.performance_report()
    assert report["total_trades"] == 1
    print(f"  Total trades: {report['total_trades']}")
    print(f"  Total P/L: ${report['total_profit']:.2f}")

    j.close()
    os.unlink(tmp)
    print("  [PASS] Journal working")
    print()


def test_backtest():
    print("=== Testing Backtest ===")
    bt = BacktestEngine()

    data = generate_multi_tf("up")
    result = bt.run_backtest(data, initial_balance=10000)

    assert isinstance(result, BacktestResult), "Should return BacktestResult"
    print(f"  Total trades: {result.total_trades}")
    print(f"  Win rate: {result.win_rate}%")
    print(f"  Profit factor: {result.profit_factor}")
    print(f"  Total P/L: ${result.total_profit:.2f}")
    print(f"  Max DD: {result.max_drawdown_percent}%")
    print(f"  Start: ${result.start_balance:.2f}")
    print(f"  End: ${result.end_balance:.2f}")

    if result.trades:
        mc = bt.monte_carlo(result.trades, n_simulations=100)
        print(f"\n  Monte Carlo (100 sims):")
        print(f"    Median: ${mc['median_balance']:.2f}")
        print(f"    Profit prob: {mc['probability_of_profit']}%")

    print("  [PASS] Backtest working")
    print()


def main():
    print("\n" + "=" * 60)
    print("MT5 AUTONOMOUS TRADING SYSTEM - TEST SUITE")
    print("=" * 60 + "\n")

    tests = [
        test_config,
        test_frame_engine,
        test_cycle_engine,
        test_trend_engine,
        test_price_action,
        test_signal_engine,
        test_risk_manager,
        test_journal,
        test_backtest,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            failed += 1

    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
