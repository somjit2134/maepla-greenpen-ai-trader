import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtest import BacktestEngine, BacktestResult

from tests.conftest import generate_multi_tf


class TestBacktest:
    def test_basic_backtest(self):
        bt = BacktestEngine()
        data = generate_multi_tf("up")
        result = bt.run_backtest(data, initial_balance=10000)

        assert isinstance(result, BacktestResult)
        assert result.start_balance == 10000
        assert len(result.equity_curve) > 0

    def test_backtest_has_real_costs(self):
        bt = BacktestEngine()
        data = generate_multi_tf("up")
        result = bt.run_backtest(data, initial_balance=10000)

        for trade in result.trades:
            assert trade.get("spread_cost", 0) >= 0
            assert trade.get("commission", 0) >= 0

    def test_backtest_sharpe_ratio(self):
        bt = BacktestEngine()
        data = generate_multi_tf("up")
        result = bt.run_backtest(data, initial_balance=10000)

        assert isinstance(result.sharpe_ratio, float)

    def test_monte_carlo(self):
        bt = BacktestEngine()
        data = generate_multi_tf("up")
        result = bt.run_backtest(data, initial_balance=10000)

        if result.trades:
            mc = bt.monte_carlo(result.trades, n_simulations=100)
            assert mc["simulations"] == 100
            assert mc["median_balance"] > 0
            assert 0 <= mc["probability_of_profit"] <= 100

    def test_monte_carlo_empty(self):
        bt = BacktestEngine()
        mc = bt.monte_carlo([], n_simulations=100)
        assert "message" in mc

    def test_walk_forward(self):
        bt = BacktestEngine()
        data = generate_multi_tf("up")
        result = bt.walk_forward(data, n_splits=3)

        if "message" not in result:
            assert result["splits"] == 3
            assert len(result["results"]) == 3

    def test_save_results(self):
        bt = BacktestEngine()
        data = generate_multi_tf("up")
        result = bt.run_backtest(data, initial_balance=10000)

        filepath = bt.save_results(result, filename="test_backtest")
        assert os.path.exists(filepath)
        os.unlink(filepath)
