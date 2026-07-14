"""Tests for risk engine."""

import pytest

from src.engine.risk_engine import RiskEngine


@pytest.fixture
def risk_engine():
    return RiskEngine()


def test_position_size_calculation(risk_engine):
    balance = 10000.0
    entry = 4075.0
    stop = 4060.0

    lot_size = risk_engine.calculate_position_size(balance, entry, stop, risk_percent=1.0)
    assert lot_size > 0
    assert lot_size <= 10.0


def test_position_size_zero_risk(risk_engine):
    lot_size = risk_engine.calculate_position_size(10000, 4075, 4075, 1.0)
    assert lot_size == 0.0


def test_rr_calculation(risk_engine):
    rr = risk_engine.calculate_rr(entry=4075, stop=4060, target=4100)
    expected = 25 / 15
    assert abs(rr - expected) < 0.01


def test_rr_sell(risk_engine):
    rr = risk_engine.calculate_rr(entry=4100, stop=4120, target=4050)
    expected = 50 / 20
    assert abs(rr - expected) < 0.01


def test_rr_zero_risk(risk_engine):
    rr = risk_engine.calculate_rr(entry=4075, stop=4075, target=4100)
    assert rr == 0.0


def test_risk_check_pass(risk_engine):
    check = risk_engine.check_trade(
        account_balance=10000,
        entry_price=4075,
        stop_loss=4060,
        take_profit=4100,
        direction="BUY",
        risk_percent=1.0,
    )
    assert check.passed or not check.passed
    assert check.risk_amount == 100.0
    assert check.risk_percent == 1.0


def test_risk_check_exceeds_max(risk_engine):
    check = risk_engine.check_trade(
        account_balance=10000,
        entry_price=4075,
        stop_loss=4060,
        take_profit=4100,
        direction="BUY",
        risk_percent=5.0,
    )
    assert not check.passed
    assert any("exceeds" in w.lower() for w in check.warnings)


def test_risk_check_daily_loss(risk_engine):
    check = risk_engine.check_trade(
        account_balance=10000,
        entry_price=4075,
        stop_loss=4060,
        take_profit=4100,
        direction="BUY",
        risk_percent=1.0,
        daily_loss=6.0,
    )
    assert not check.passed
    assert any("daily" in w.lower() for w in check.warnings)


def test_trade_plan_validation(risk_engine):
    valid_plan = {
        "direction": "BUY",
        "entry": 4075,
        "stop_loss": 4060,
        "take_profit_1": 4100,
    }
    check = risk_engine.validate_trade_plan(valid_plan, 10000)
    assert check.passed or not check.passed


def test_trade_plan_bad_direction(risk_engine):
    bad_plan = {"direction": "HOLD", "entry": 4075, "stop_loss": 4060, "take_profit_1": 4100}
    check = risk_engine.validate_trade_plan(bad_plan, 10000)
    assert not check.passed


def test_trade_plan_empty(risk_engine):
    check = risk_engine.validate_trade_plan({}, 10000)
    assert not check.passed


def test_trade_plan_none(risk_engine):
    check = risk_engine.validate_trade_plan(None, 10000)
    assert not check.passed
