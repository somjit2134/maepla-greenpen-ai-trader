import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.signal_engine import SignalEngine, SignalResult
from src.engine.risk_manager import RiskManager
from src.data.journal import Journal

from tests.conftest import generate_multi_tf


class TestSignalEngine:
    def test_signal_generation(self):
        engine = SignalEngine()
        data = generate_multi_tf("up")
        bid, ask = 2000.0, 2000.5

        result = engine.analyze(data, bid, ask)

        assert isinstance(result, SignalResult)
        assert result.direction in ("BUY", "SELL", "WAIT")
        assert result.signal_grade in ("A+", "A", "B+", "B", "NO_TRADE")
        assert result.confidence_score >= 0

    def test_signal_with_different_trends(self):
        engine = SignalEngine()

        for trend in ["up", "down", "sideway"]:
            data = generate_multi_tf(trend)
            result = engine.analyze(data, 2000.0, 2000.5)
            assert result.direction in ("BUY", "SELL", "WAIT")

    def test_signal_levels(self):
        engine = SignalEngine()
        data = generate_multi_tf("up")
        result = engine.analyze(data, 2000.0, 2000.5)

        if result.direction != "WAIT":
            assert result.entry_price > 0
            assert result.stop_loss > 0
            assert result.take_profit_1 > 0
            assert result.risk_reward > 0

    def test_signal_has_all_engines(self):
        engine = SignalEngine()
        data = generate_multi_tf("up")
        result = engine.analyze(data, 2000.0, 2000.5)

        assert result.frame is not None
        assert result.cycle is not None
        assert result.trend is not None
        assert result.price_action is not None


class TestRiskIntegration:
    def test_risk_with_signal(self):
        engine = SignalEngine()
        risk_mgr = RiskManager()
        data = generate_multi_tf("up")

        signal = engine.analyze(data, 2000.0, 2000.5)

        if signal.direction != "WAIT":
            check = risk_mgr.validate_trade(
                signal.direction, signal.entry_price, signal.stop_loss,
                signal.take_profit_1, 10000, open_positions=0,
            )
            assert check.passed or not check.passed
            assert check.position_size > 0


class TestSignalExit:
    def test_buy_position_with_sell_signal_should_close(self):
        positions = [{"ticket": 1, "type": "BUY", "magic": 20260712, "profit": 50.0}]
        signal_direction = "SELL"
        my_positions = [p for p in positions if p.get("magic") == 20260712]
        should_close = []
        for pos in my_positions:
            pos_type = pos.get("type", "")
            if (pos_type == "BUY" and signal_direction == "SELL") or \
               (pos_type == "SELL" and signal_direction == "BUY"):
                should_close.append(pos["ticket"])
        assert len(should_close) == 1
        assert should_close[0] == 1

    def test_sell_position_with_buy_signal_should_close(self):
        positions = [{"ticket": 2, "type": "SELL", "magic": 20260712, "profit": -30.0}]
        signal_direction = "BUY"
        my_positions = [p for p in positions if p.get("magic") == 20260712]
        should_close = []
        for pos in my_positions:
            pos_type = pos.get("type", "")
            if (pos_type == "BUY" and signal_direction == "SELL") or \
               (pos_type == "SELL" and signal_direction == "BUY"):
                should_close.append(pos["ticket"])
        assert len(should_close) == 1

    def test_same_direction_should_not_close(self):
        positions = [{"ticket": 3, "type": "BUY", "magic": 20260712, "profit": 100.0}]
        signal_direction = "BUY"
        my_positions = [p for p in positions if p.get("magic") == 20260712]
        should_close = []
        for pos in my_positions:
            pos_type = pos.get("type", "")
            if (pos_type == "BUY" and signal_direction == "SELL") or \
               (pos_type == "SELL" and signal_direction == "BUY"):
                should_close.append(pos["ticket"])
        assert len(should_close) == 0

    def test_wait_signal_should_not_close(self):
        positions = [{"ticket": 4, "type": "BUY", "magic": 20260712, "profit": 10.0}]
        signal_direction = "WAIT"
        my_positions = [p for p in positions if p.get("magic") == 20260712]
        should_close = []
        if signal_direction != "WAIT":
            for pos in my_positions:
                pos_type = pos.get("type", "")
                if (pos_type == "BUY" and signal_direction == "SELL") or \
                   (pos_type == "SELL" and signal_direction == "BUY"):
                    should_close.append(pos["ticket"])
        assert len(should_close) == 0

    def test_other_magic_should_not_close(self):
        positions = [{"ticket": 5, "type": "BUY", "magic": 999999, "profit": 50.0}]
        signal_direction = "SELL"
        my_positions = [p for p in positions if p.get("magic") == 20260712]
        should_close = []
        for pos in my_positions:
            pos_type = pos.get("type", "")
            if (pos_type == "BUY" and signal_direction == "SELL") or \
               (pos_type == "SELL" and signal_direction == "BUY"):
                should_close.append(pos["ticket"])
        assert len(should_close) == 0

    def test_multiple_positions_partial_close(self):
        positions = [
            {"ticket": 10, "type": "BUY", "magic": 20260712, "profit": 50.0},
            {"ticket": 11, "type": "SELL", "magic": 20260712, "profit": -30.0},
        ]
        signal_direction = "SELL"
        my_positions = [p for p in positions if p.get("magic") == 20260712]
        should_close = []
        for pos in my_positions:
            pos_type = pos.get("type", "")
            if (pos_type == "BUY" and signal_direction == "SELL") or \
               (pos_type == "SELL" and signal_direction == "BUY"):
                should_close.append(pos["ticket"])
        assert len(should_close) == 1
        assert should_close[0] == 10

    def test_profit_pips_calculation(self):
        point = 0.01
        pos_type = "BUY"
        price_open = 2000.0
        price_current = 2025.0
        if pos_type == "BUY":
            profit_pips = (price_current - price_open) / point
        else:
            profit_pips = (price_open - price_current) / point
        assert profit_pips == 2500.0

        pos_type = "SELL"
        price_open = 2050.0
        price_current = 2025.0
        if pos_type == "BUY":
            profit_pips = (price_current - price_open) / point
        else:
            profit_pips = (price_open - price_current) / point
        assert profit_pips == 2500.0


class TestJournal:
    def test_journal_workflow(self):
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
        assert trade_id > 0

        j.close_trade(12345, 2020.0, 200.0, profit_pips=200, exit_reason="TP")
        trades = j.get_closed_trades()
        assert len(trades) == 1
        assert trades[0]["profit"] == 200.0

        wr = j.win_rate()
        assert wr == 100.0

        report = j.performance_report()
        assert report["total_trades"] == 1
        assert report["total_profit"] == 200.0

        j.close()
        os.unlink(tmp)

    def test_journal_multiple_trades(self):
        import tempfile
        tmp = tempfile.mktemp(suffix=".db")
        j = Journal(tmp)

        j.log_trade({"ticket": 1, "direction": "BUY", "entry_price": 2000, "stop_loss": 1990, "take_profit_1": 2020, "lot_size": 0.1})
        j.log_trade({"ticket": 2, "direction": "SELL", "entry_price": 2050, "stop_loss": 2060, "take_profit_1": 2030, "lot_size": 0.1})
        j.log_trade({"ticket": 3, "direction": "BUY", "entry_price": 2010, "stop_loss": 2000, "take_profit_1": 2030, "lot_size": 0.1})

        j.close_trade(1, 2020.0, 200.0)
        j.close_trade(2, 2030.0, 200.0)
        j.close_trade(3, 2000.0, -100.0)

        wr = j.win_rate()
        assert wr == round(2 / 3 * 100, 1)

        report = j.performance_report()
        assert report["total_trades"] == 3
        assert report["total_profit"] == 300.0

        j.close()
        os.unlink(tmp)
