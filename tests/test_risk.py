import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.risk_manager import RiskManager, RiskCheck


@pytest.fixture
def risk_manager():
    return RiskManager()


class TestRiskManager:
    def test_position_size_calculation(self, risk_manager):
        lot = risk_manager.calculate_position_size(10000, 2000, 1990)
        assert lot > 0
        assert lot <= 10.0

    def test_position_size_zero_risk(self, risk_manager):
        lot = risk_manager.calculate_position_size(10000, 4075, 4075, 1.0)
        assert lot == 0.0

    def test_rr_calculation(self, risk_manager):
        rr = risk_manager.calculate_rr(entry=2000, stop_loss=1990, take_profit=2020)
        assert rr == 2.0

    def test_rr_sell(self, risk_manager):
        rr = risk_manager.calculate_rr(entry=2100, stop_loss=2120, take_profit=2050)
        expected = 50 / 20
        assert abs(rr - expected) < 0.01

    def test_rr_zero_risk(self, risk_manager):
        rr = risk_manager.calculate_rr(entry=2000, stop_loss=2000, take_profit=2020)
        assert rr == 0.0

    def test_risk_check_pass(self, risk_manager):
        check = risk_manager.validate_trade(
            direction="BUY",
            entry=2000,
            stop_loss=1990,
            take_profit=2020,
            balance=10000,
            open_positions=0,
        )
        assert check.passed
        assert check.risk_amount == 100.0
        assert check.risk_percent == 1.0

    def test_risk_check_low_rr(self, risk_manager):
        check = risk_manager.validate_trade(
            direction="BUY",
            entry=2000,
            stop_loss=1990,
            take_profit=2005,
            balance=10000,
        )
        assert not check.passed
        assert any("RR" in w for w in check.warnings)

    def test_risk_check_invalid_levels(self, risk_manager):
        check = risk_manager.validate_trade(
            direction="BUY",
            entry=2000,
            stop_loss=2010,
            take_profit=2020,
            balance=10000,
        )
        assert not check.passed
        assert any("Invalid" in w for w in check.warnings)

    def test_risk_check_max_positions(self, risk_manager):
        check = risk_manager.validate_trade(
            direction="BUY",
            entry=2000,
            stop_loss=1990,
            take_profit=2020,
            balance=10000,
            open_positions=3,
        )
        assert not check.passed
        assert any("Max open" in w for w in check.warnings)

    def test_risk_check_daily_loss(self, risk_manager):
        check = risk_manager.validate_trade(
            direction="BUY",
            entry=2000,
            stop_loss=1990,
            take_profit=2020,
            balance=10000,
            daily_loss=600.0,
        )
        assert not check.passed
        assert any("Daily loss" in w for w in check.warnings)

    def test_risk_check_consecutive_losses(self, risk_manager):
        check = risk_manager.validate_trade(
            direction="BUY",
            entry=2000,
            stop_loss=1990,
            take_profit=2020,
            balance=10000,
            consecutive_losses=3,
        )
        assert not check.passed
        assert any("Consecutive" in w for w in check.warnings)

    def test_risk_check_spread(self, risk_manager):
        check = risk_manager.validate_trade(
            direction="BUY",
            entry=2000,
            stop_loss=1990,
            take_profit=2020,
            balance=10000,
            current_spread=100.0,
        )
        assert not check.passed
        assert any("Spread" in w for w in check.warnings)

    def test_record_trade_result(self, risk_manager):
        risk_manager.record_trade_result(-100)
        assert risk_manager._consecutive_losses == 1
        assert risk_manager._daily_loss == 100.0

        risk_manager.record_trade_result(-50)
        assert risk_manager._consecutive_losses == 2
        assert risk_manager._daily_loss == 150.0

        risk_manager.record_trade_result(200)
        assert risk_manager._consecutive_losses == 0

    def test_get_status(self, risk_manager):
        status = risk_manager.get_status()
        assert "daily_loss" in status
        assert "consecutive_losses" in status
        assert "max_daily_loss" in status
        assert "max_consecutive" in status
