from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.config_loader import get_config
from src.data.mt5_connector import MT5Connector
from src.data.database import Database
from src.engine.risk_engine import RiskEngine
from src.log_setup import get_logger

logger = get_logger()


@dataclass
class TradeResult:
    success: bool = False
    ticket: int = 0
    message: str = ""
    trade_id: int = 0


class TradingEngine:
    def __init__(self, connector: Optional[MT5Connector] = None, db: Optional[Database] = None):
        self.cfg = get_config()
        self.connector = connector
        self.db = db or Database()
        self.risk_engine = RiskEngine()

    def set_connector(self, connector: MT5Connector):
        self.connector = connector

    def place_trade(self, plan: dict, risk_percent: Optional[float] = None) -> TradeResult:
        if not plan:
            return TradeResult(success=False, message="No trade plan provided")

        direction = plan.get("direction", "")
        entry = plan.get("entry", 0)
        sl = plan.get("stop_loss", 0)
        tp1 = plan.get("take_profit_1", 0)
        tp2 = plan.get("take_profit_2")

        if not self.connector or not self.connector.is_connected():
            return TradeResult(success=False, message="MT5 not connected")

        account = self.connector.get_account_info()
        if not account:
            return TradeResult(success=False, message="Cannot get account info")

        balance = account["balance"]

        risk_check = self.risk_engine.validate_trade_plan(plan, balance)
        if not risk_check.passed:
            logger.warning(f"Trade rejected: {risk_check.warnings}")
            return TradeResult(
                success=False,
                message=f"Risk check failed: {'; '.join(risk_check.warnings)}",
            )

        lot_size = risk_check.position_size
        if lot_size <= 0:
            return TradeResult(success=False, message="Invalid lot size")

        try:
            import MetaTrader5 as mt5

            order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

            price = mt5.symbol_info_tick(self.cfg.symbol.name)

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.cfg.symbol.name,
                "volume": lot_size,
                "type": order_type,
                "price": price.ask if direction == "BUY" else price.bid,
                "sl": sl,
                "tp": tp1,
                "deviation": 20,
                "magic": 202407,
                "comment": "MaePlaGreenPen",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Order failed: retcode={result.retcode}, comment={result.comment}")
                return TradeResult(
                    success=False,
                    message=f"Order failed: {result.comment} (code {result.retcode})",
                )

            logger.info(f"Trade placed: {direction} {lot_size} lots @ {price}, ticket={result.order}")

            trade_data = {
                "signal_id": None,
                "timestamp": pd.Timestamp.now().isoformat(),
                "symbol": self.cfg.symbol.name,
                "direction": direction,
                "entry_price": price.ask if direction == "BUY" else price.bid,
                "stop_loss": sl,
                "take_profit1": tp1,
                "take_profit2": tp2,
                "lot_size": lot_size,
                "risk_percent": risk_check.risk_percent,
                "risk_reward": risk_check.rr_ratio,
                "status": "OPEN",
            }
            trade_id = self.db.save_trade(trade_data)

            return TradeResult(
                success=True,
                ticket=result.order,
                message=f"Trade #{result.order} executed",
                trade_id=trade_id,
            )

        except ImportError:
            logger.error("MetaTrader5 not installed for trade execution")
            return TradeResult(success=False, message="MetaTrader5 not installed")
        except Exception as e:
            logger.exception(f"Trade execution error")
            return TradeResult(success=False, message=str(e))

    def close_position(self, ticket: int) -> bool:
        try:
            import MetaTrader5 as mt5

            position = mt5.positions_get(ticket=ticket)
            if not position:
                logger.warning(f"Position #{ticket} not found")
                return False

            pos = position[0]
            order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(pos.symbol)

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": order_type,
                "position": ticket,
                "price": price.bid if order_type == mt5.ORDER_TYPE_SELL else price.ask,
                "deviation": 20,
                "magic": 202407,
                "comment": "MaePlaGreenPen_Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Close failed: {result.comment}")
                return False

            profit = pos.profit
            open_trades = self.db.get_open_trades()
            for t in open_trades:
                self.db.close_trade(t["id"], price.bid, profit)

            logger.info(f"Position #{ticket} closed, profit={profit:.2f}")
            return True

        except ImportError:
            logger.error("MetaTrader5 not installed")
            return False
        except Exception as e:
            logger.exception(f"Close position error")
            return False

    def get_open_positions(self) -> list[dict]:
        try:
            import MetaTrader5 as mt5
            positions = mt5.positions_get(symbol=self.cfg.symbol.name)
            if not positions:
                return []
            return [
                {
                    "ticket": p.ticket,
                    "type": "BUY" if p.type == 0 else "SELL",
                    "volume": p.volume,
                    "price": p.price_open,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": p.profit,
                    "swap": p.swap,
                }
                for p in positions
            ]
        except ImportError:
            return []

    def get_account_summary(self) -> dict:
        if not self.connector or not self.connector.is_connected():
            return {}
        info = self.connector.get_account_info()
        if not info:
            return {}
        positions = self.get_open_positions()
        open_profit = sum(p.get("profit", 0) for p in positions)
        info["open_positions"] = len(positions)
        info["open_profit"] = round(open_profit, 2)
        return info
