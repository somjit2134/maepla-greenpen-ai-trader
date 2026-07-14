from src.config import get
from src.logger import get_logger

logger = get_logger()


class RiskManager:
    def __init__(self):
        self.cfg = get()

    def position_size(self, balance: float, entry: float, stop: float,
                      risk_pct: float | None = None) -> float:
        pct = min(risk_pct or self.cfg.risk.default_risk_percent,
                  self.cfg.risk.max_risk_percent)
        risk_amt = balance * (pct / 100)
        dist = abs(entry - stop)
        if dist <= 0:
            return 0.0
        raw = risk_amt / (dist * 100)
        step = self.cfg.symbol.volume_step
        lots = round(raw / step) * step
        lots = max(self.cfg.symbol.min_volume,
                   min(lots, self.cfg.symbol.max_volume))
        return round(lots, 2)

    def rr(self, entry: float, stop: float, target: float) -> float:
        r = abs(entry - stop)
        if r == 0:
            return 0.0
        return round(abs(target - entry) / r, 2)

    def check(self, balance: float, entry: float, stop: float, target: float,
              direction: str, risk_pct: float | None = None,
              daily_loss: float = 0) -> dict:
        warnings = []
        pct = risk_pct or self.cfg.risk.default_risk_percent

        if pct > self.cfg.risk.max_risk_percent:
            warnings.append(f"risk {pct}% > max {self.cfg.risk.max_risk_percent}%")

        r = self.rr(entry, stop, target)
        if r < self.cfg.risk.min_rr:
            warnings.append(f"RR {r}:1 < min {self.cfg.risk.min_rr}:1")

        if daily_loss >= self.cfg.risk.max_daily_loss_percent:
            warnings.append(f"daily loss {daily_loss:.1f}% >= max {self.cfg.risk.max_daily_loss_percent}%")

        lots = self.position_size(balance, entry, stop, pct)
        risk_amt = balance * (pct / 100)

        return {
            "passed": len(warnings) == 0,
            "warnings": warnings,
            "lot_size": lots,
            "risk_amount": round(risk_amt, 2),
            "risk_percent": pct,
            "rr_ratio": r,
        }

    def validate_plan(self, plan: dict, balance: float) -> dict:
        if not plan:
            return {"passed": False, "warnings": ["no plan"]}
        if plan.get("direction") not in ("BUY", "SELL"):
            return {"passed": False, "warnings": ["invalid direction"]}

        entry = plan.get("entry", 0)
        sl = plan.get("sl", 0)
        tp = plan.get("tp1", 0)

        if plan["direction"] == "BUY" and (sl >= entry or tp <= entry):
            return {"passed": False, "warnings": ["invalid levels for BUY"]}
        if plan["direction"] == "SELL" and (sl <= entry or tp >= entry):
            return {"passed": False, "warnings": ["invalid levels for SELL"]}

        return self.check(balance, entry, sl, tp, plan["direction"])

    def can_open_trade(self, open_trades: int, daily_pnl: dict) -> tuple[bool, str]:
        if open_trades >= self.cfg.risk.max_open_trades:
            return False, f"max open trades ({self.cfg.risk.max_open_trades})"
        dp = daily_pnl.get("net_pnl", 0)
        bal = self.cfg.symbol.at  # fallback
        if dp < 0 and abs(dp) / (bal or 1) * 100 >= self.cfg.risk.max_daily_loss_percent:
            return False, f"daily loss limit hit ({dp:.2f})"
        return True, "ok"
