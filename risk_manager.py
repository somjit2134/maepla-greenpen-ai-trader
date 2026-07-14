"""
MT5 Autonomous Trading System - Risk Management Engine
========================================================
Rules:
  - Risk per trade: 1% of account
  - Max daily loss: 5%
  - Max open positions: 3
  - Max consecutive losses: 3 -> pause trading
  - Minimum RR: 1:2
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from config import get_config

logger = logging.getLogger("risk_manager")


@dataclass
class RiskCheck:
    passed: bool = False
    position_size: float = 0.0
    risk_amount: float = 0.0
    risk_percent: float = 0.0
    rr_ratio: float = 0.0
    actual_risk_percent: float = 0.0
    warnings: list = field(default_factory=list)


class RiskManager:
    """Risk Management Engine - validate and size trades."""

    def __init__(self):
        self.cfg = get_config()
        self._daily_loss = 0.0
        self._consecutive_losses = 0
        self._last_reset_date: date = date.today()

    def _check_auto_reset(self):
        """Reset daily counters automatically at midnight."""
        today = date.today()
        if today != self._last_reset_date:
            logger.info(f"New day detected, resetting daily counters (was {self._daily_loss:.2f} loss, {self._consecutive_losses} consecutive losses)")
            self._daily_loss = 0.0
            self._consecutive_losses = 0
            self._last_reset_date = today

    def calculate_position_size(
        self,
        balance: float,
        entry: float,
        stop_loss: float,
        risk_percent: Optional[float] = None,
    ) -> float:
        risk_pct = risk_percent or self.cfg.risk.risk_per_trade_percent
        risk_pct = min(risk_pct, self.cfg.risk.max_risk_percent)

        risk_amount = balance * (risk_pct / 100)
        sl_distance = abs(entry - stop_loss)

        if sl_distance <= 0:
            return 0.0

        lot_size = risk_amount / (sl_distance * self.cfg.symbol.contract_size)
        lot_size = round(lot_size, 2)
        lot_size = max(self.cfg.risk.default_lot, min(lot_size, self.cfg.risk.max_lot))

        return lot_size

    def calculate_actual_risk_percent(
        self,
        balance: float,
        lot_size: float,
        entry: float,
        stop_loss: float,
    ) -> float:
        """Calculate the actual risk percentage after lot size clamping."""
        if balance <= 0:
            return 0.0
        sl_distance = abs(entry - stop_loss)
        actual_risk = lot_size * sl_distance * self.cfg.symbol.contract_size
        return round((actual_risk / balance) * 100, 2)

    def validate_lot_size(self, lot_size: float, symbol_info: Optional[dict] = None) -> tuple[float, list]:
        """Validate lot size against broker constraints. Returns (adjusted_lot, warnings)."""
        warnings = []
        if symbol_info is None:
            return lot_size, warnings

        volume_min = symbol_info.get("volume_min", 0.01)
        volume_max = symbol_info.get("volume_max", 100.0)
        volume_step = symbol_info.get("volume_step", 0.01)

        if lot_size < volume_min:
            warnings.append(f"Lot {lot_size} below broker min {volume_min}, adjusted to {volume_min}")
            lot_size = volume_min

        if lot_size > volume_max:
            warnings.append(f"Lot {lot_size} above broker max {volume_max}, adjusted to {volume_max}")
            lot_size = volume_max

        if volume_step > 0:
            steps = round(lot_size / volume_step)
            adjusted = steps * volume_step
            if abs(adjusted - lot_size) > 1e-10:
                warnings.append(f"Lot {lot_size} rounded to broker step {volume_step}: {adjusted}")
                lot_size = adjusted

        return lot_size, warnings

    def calculate_rr(self, entry: float, stop_loss: float, take_profit: float) -> float:
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        if risk == 0:
            return 0.0
        return round(reward / risk, 2)

    def validate_trade(
        self,
        direction: str,
        entry: float,
        stop_loss: float,
        take_profit: float,
        balance: float,
        open_positions: int = 0,
        daily_loss: Optional[float] = None,
        consecutive_losses: Optional[int] = None,
        current_spread: float = 0.0,
        margin_free: float = 0.0,
        symbol_info: Optional[dict] = None,
    ) -> RiskCheck:
        self._check_auto_reset()

        check = RiskCheck(warnings=[])

        if direction not in ("BUY", "SELL"):
            check.warnings.append("Invalid direction")
            return check

        if direction == "BUY" and (stop_loss >= entry or take_profit <= entry):
            check.warnings.append("Invalid BUY levels: SL must be below entry, TP above")
            return check

        if direction == "SELL" and (stop_loss <= entry or take_profit >= entry):
            check.warnings.append("Invalid SELL levels: SL must be above entry, TP below")
            return check

        rr = self.calculate_rr(entry, stop_loss, take_profit)
        check.rr_ratio = rr
        if rr < self.cfg.risk.min_rr:
            check.warnings.append(f"RR {rr}:1 below minimum {self.cfg.risk.min_rr}:1")

        if open_positions >= self.cfg.risk.max_open_positions:
            check.warnings.append(f"Max open positions ({self.cfg.risk.max_open_positions}) reached")

        effective_daily_loss = daily_loss if daily_loss is not None else self._daily_loss
        daily_loss_pct = (effective_daily_loss / balance * 100) if balance > 0 else 0.0
        if daily_loss_pct >= self.cfg.risk.max_daily_loss_percent:
            check.warnings.append(f"Daily loss limit ({self.cfg.risk.max_daily_loss_percent}%) reached: {daily_loss_pct:.1f}%")

        effective_consecutive = consecutive_losses if consecutive_losses is not None else self._consecutive_losses
        if effective_consecutive >= self.cfg.risk.max_consecutive_losses:
            check.warnings.append(f"Consecutive losses ({effective_consecutive}) limit reached")

        if current_spread > self.cfg.symbol.spread_max:
            check.warnings.append(f"Spread {current_spread:.0f} pts exceeds max {self.cfg.symbol.spread_max:.0f} pts")

        risk_pct = self.cfg.risk.risk_per_trade_percent
        risk_amount = balance * (risk_pct / 100)
        check.risk_amount = round(risk_amount, 2)
        check.risk_percent = risk_pct

        lot_size = self.calculate_position_size(balance, entry, stop_loss, risk_pct)

        if symbol_info:
            lot_size, volume_warnings = self.validate_lot_size(lot_size, symbol_info)
            check.warnings.extend(volume_warnings)

        if margin_free > 0 and lot_size > 0:
            sl_distance = abs(entry - stop_loss)
            required_margin = lot_size * sl_distance * self.cfg.symbol.contract_size
            if required_margin > margin_free:
                check.warnings.append(f"Insufficient margin: need ${required_margin:.2f}, free ${margin_free:.2f}")

        check.position_size = lot_size
        check.actual_risk_percent = self.calculate_actual_risk_percent(balance, lot_size, entry, stop_loss)

        if check.actual_risk_percent > risk_pct * 1.5:
            check.warnings.append(f"Actual risk {check.actual_risk_percent:.1f}% exceeds target {risk_pct:.1f}% (min lot clamp)")

        check.passed = len(check.warnings) == 0

        if check.passed:
            logger.info(f"Risk check PASSED: {direction} {lot_size} lots, RR {rr}:1, actual risk {check.actual_risk_percent:.1f}%")
        else:
            for w in check.warnings:
                logger.warning(f"Risk check FAILED: {w}")

        return check

    def record_trade_result(self, profit: float):
        if profit < 0:
            self._consecutive_losses += 1
            self._daily_loss += abs(profit)
        else:
            self._consecutive_losses = 0

    def reset_daily(self):
        self._daily_loss = 0.0
        self._consecutive_losses = 0

    def get_status(self) -> dict:
        return {
            "daily_loss": self._daily_loss,
            "consecutive_losses": self._consecutive_losses,
            "max_daily_loss": self.cfg.risk.max_daily_loss_percent,
            "max_consecutive": self.cfg.risk.max_consecutive_losses,
        }
