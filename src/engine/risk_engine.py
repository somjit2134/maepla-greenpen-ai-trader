from dataclasses import dataclass
from typing import Optional

from src.config_loader import get_config
from src.log_setup import get_logger

logger = get_logger()


@dataclass
class RiskCheck:
    passed: bool = True
    position_size: float = 0.0
    risk_amount: float = 0.0
    risk_percent: float = 0.0
    rr_ratio: float = 0.0
    warnings: list = None


class RiskEngine:
    def __init__(self):
        self.cfg = get_config()

    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        risk_percent: Optional[float] = None,
    ) -> float:
        risk_pct = risk_percent or self.cfg.risk.default_risk_percent
        risk_pct = min(risk_pct, self.cfg.risk.max_risk_percent)

        risk_amount = account_balance * (risk_pct / 100)
        sl_distance = abs(entry_price - stop_loss)

        if sl_distance <= 0:
            logger.error("Stop loss distance is zero or negative")
            return 0.0

        lot_size = risk_amount / (sl_distance * 100)

        lot_size = round(lot_size, 2)
        lot_size = max(0.01, min(lot_size, 10.0))

        logger.info(
            f"Position size: {lot_size:.2f} lots, Risk: ${risk_amount:.2f} ({risk_pct:.1f}%)"
        )
        return lot_size

    def calculate_rr(self, entry: float, stop: float, target: float) -> float:
        risk = abs(entry - stop)
        reward = abs(target - entry)
        if risk == 0:
            return 0.0
        return round(reward / risk, 2)

    def check_trade(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        direction: str,
        risk_percent: Optional[float] = None,
        daily_loss: float = 0.0,
    ) -> RiskCheck:
        check = RiskCheck(warnings=[])

        risk_pct = risk_percent or self.cfg.risk.default_risk_percent
        if risk_pct > self.cfg.risk.max_risk_percent:
            check.passed = False
            check.warnings.append(
                f"Risk {risk_pct}% exceeds max {self.cfg.risk.max_risk_percent}%"
            )

        rr = self.calculate_rr(entry_price, stop_loss, take_profit)
        check.rr_ratio = rr
        if rr < self.cfg.risk.min_rr:
            check.passed = False
            check.warnings.append(
                f"RR {rr}:1 below minimum {self.cfg.risk.min_rr}:1"
            )

        risk_amount = account_balance * (risk_pct / 100)
        check.risk_amount = risk_amount
        check.risk_percent = risk_pct

        if daily_loss >= self.cfg.risk.max_daily_loss_percent:
            check.passed = False
            check.warnings.append(
                f"Daily loss {daily_loss:.1f}% exceeds max {self.cfg.risk.max_daily_loss_percent}%"
            )

        lot_size = self.calculate_position_size(
            account_balance, entry_price, stop_loss, risk_pct
        )
        check.position_size = lot_size

        if not check.warnings:
            logger.info("Risk check PASSED")
        else:
            for w in check.warnings:
                logger.warning(f"Risk warning: {w}")

        return check

    def validate_trade_plan(self, plan: dict, balance: float) -> RiskCheck:
        if not plan:
            return RiskCheck(passed=False, warnings=["No trade plan"])

        direction = plan.get("direction", "")
        entry = plan.get("entry", 0)
        sl = plan.get("stop_loss", 0)
        tp = plan.get("take_profit_1", 0)

        if direction not in ("BUY", "SELL"):
            return RiskCheck(passed=False, warnings=["Invalid direction"])

        if direction == "BUY" and (sl >= entry or tp <= entry):
            return RiskCheck(passed=False, warnings=["Invalid levels for BUY"])

        if direction == "SELL" and (sl <= entry or tp >= entry):
            return RiskCheck(passed=False, warnings=["Invalid levels for SELL"])

        return self.check_trade(balance, entry, sl, tp, direction)
