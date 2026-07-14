from datetime import datetime

import pandas as pd

from src.config import get
from src.connector import MT5Connector
from src.database import Database
from src.risk import RiskManager
from src.logger import get_logger

logger = get_logger()


class TradingEngine:
    def __init__(self, connector: MT5Connector | None = None, db: Database | None = None):
        self.cfg = get()
        self.connector = connector
        self.db = db or Database()
        self.risk = RiskManager()

    def set_connector(self, c):
        self.connector = c

    def execute(self, plan: dict, analysis_id: int = 0, balance: float = 10000) -> dict:
        if not plan:
            return {"success": False, "msg": "no plan"}

        direction = plan["direction"]
        entry = plan["entry"]
        sl = plan["sl"]
        tp1 = plan["tp1"]

        rc = self.risk.validate_plan(plan, balance)
        if not rc["passed"]:
            logger.warning(f"Trade rejected: {'; '.join(rc['warnings'])}")
            return {"success": False, "msg": "; ".join(rc["warnings"])}

        lots = rc["lot_size"]
        if lots <= 0:
            return {"success": False, "msg": "invalid lot size"}

        bid, ask, spread = self.connector.tick()
        if spread > self.cfg.risk.max_spread:
            return {"success": False, "msg": f"spread {spread} > max {self.cfg.risk.max_spread}"}

        try:
            import MetaTrader5 as mt5
            order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
            price = ask if direction == "BUY" else bid

            filling = self.connector.get_symbol_filling()

            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.cfg.symbol.name,
                "volume": lots,
                "type": order_type,
                "price": price,
                "sl": sl,
                "tp": tp1,
                "deviation": self.cfg.risk.slippage,
                "magic": 20260709,
                "comment": "MaePlaAuto",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }

            logger.info(f"Sending order: {direction} {lots} lots @ {price:.2f} filling={filling}")
            r = self.connector.order_send(req)
            if r is None:
                logger.error(f"Order send returned None: {self.connector.mt5.last_error()}")
                return {"success": False, "msg": f"order send returned None"}

            success_codes = {0, 10009}
            if r["retcode"] not in success_codes:
                logger.error(f"Order failed retcode={r['retcode']} comment={r.get('comment','')} details={r}")
                return {"success": False, "msg": f"retcode={r['retcode']} {r.get('comment','')}"}

            logger.info(f"Order executed: {direction} {lots} lots @ {price:.2f} ticket={r['ticket']}")

            order_data = {
                "signal_id": analysis_id,
                "ticket": r["ticket"],
                "time": datetime.now().isoformat(),
                "symbol": self.cfg.symbol.name,
                "direction": direction,
                "volume": lots,
                "entry_price": price,
                "stop_loss": sl,
                "take_profit": tp1,
                "risk_pct": rc["risk_percent"],
                "rr": rc["rr_ratio"],
                "status": "OPEN",
            }
            order_id = self.db.save_order(order_data)

            return {"success": True, "ticket": r["ticket"], "order_id": order_id,
                    "msg": f"trade #{r['ticket']} executed", "lot_size": lots}

        except ImportError:
            logger.error("MetaTrader5 package not installed. Run: pip install MetaTrader5")
            return {"success": False, "msg": "MetaTrader5 package not installed"}
        except Exception as e:
            logger.exception("execution error")
            return {"success": False, "msg": str(e)}

    def close_position(self, ticket: int) -> dict:
        try:
            import MetaTrader5 as mt5

            positions = self.connector.positions()
            pos = None
            for p in positions:
                if p["ticket"] == ticket:
                    pos = p
                    break

            if pos is None:
                return {"success": False, "msg": f"position {ticket} not found"}

            ot = mt5.ORDER_TYPE_SELL if pos["type"] == "BUY" else mt5.ORDER_TYPE_BUY
            bid, ask, spread = self.connector.tick()
            price = bid if ot == mt5.ORDER_TYPE_SELL else ask

            filling = self.connector.get_symbol_filling()

            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.cfg.symbol.name,
                "volume": pos["volume"],
                "type": ot,
                "position": ticket,
                "price": price,
                "deviation": self.cfg.risk.slippage,
                "magic": 20260709,
                "comment": "MaePlaAuto_Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }
            r = self.connector.order_send(req)
            if r is None or r["retcode"] not in {0, 10009}:
                return {"success": False, "msg": f"close failed retcode={r['retcode'] if r else 'None'}"}

            profit = pos.get("profit", 0)
            open_orders = self.db.get_open_orders()
            for o in open_orders:
                if o.get("ticket") == ticket:
                    self.db.close_order(o["id"], price, profit, "manual close")

            self.db.update_daily_pnl()
            return {"success": True, "profit": profit, "msg": f"closed #{ticket}"}

        except ImportError:
            return {"success": False, "msg": "MetaTrader5 package not installed"}
        except Exception as e:
            logger.exception("close_position error")
            return {"success": False, "msg": str(e)}

    def get_positions(self) -> list[dict]:
        return self.connector.positions() if self.connector else []

    def get_account(self) -> dict:
        return self.connector.account() if self.connector else {}
