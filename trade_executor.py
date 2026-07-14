"""
MT5 Autonomous Trading System - Trade Execution Engine
========================================================
Executes and manages trades:
  - Place BUY/SELL orders
  - Break even management
  - Trailing stop
  - Partial close
  - Emergency exit
"""
import time
import logging
from dataclasses import dataclass
from typing import Optional

from config import get_config

logger = logging.getLogger("trade_executor")


@dataclass
class TradeResult:
    success: bool = False
    ticket: int = 0
    message: str = ""
    price: float = 0.0


class TradeExecutor:
    """Trade Execution Engine - auto execute and manage trades."""

    def __init__(self, connector=None):
        self.cfg = get_config()
        self.connector = connector
        self._max_retries = 3
        self._retry_delay = 2

    def set_connector(self, connector):
        self.connector = connector

    def _check_spread(self, symbol: str) -> tuple[bool, float]:
        """Check if current spread is within allowed max. Returns (ok, spread_pts)."""
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return True, 0.0

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return False, 0.0

        spread_pts = (tick.ask - tick.bid) / self.cfg.symbol.point
        if spread_pts > self.cfg.symbol.spread_max:
            logger.warning(f"Spread too high: {spread_pts:.0f} > {self.cfg.symbol.spread_max:.0f}")
            return False, spread_pts
        return True, spread_pts

    def place_order(
        self,
        direction: str,
        entry: float,
        stop_loss: float,
        take_profit: float,
        lot_size: float,
        comment: str = "AutoTrade",
    ) -> TradeResult:
        if not self.connector or not self.connector.is_connected():
            return TradeResult(success=False, message="MT5 not connected")

        try:
            import MetaTrader5 as mt5
        except ImportError:
            return TradeResult(success=False, message="MetaTrader5 not installed")

        symbol = self.cfg.symbol.name
        info = mt5.symbol_info(symbol)
        if info is None:
            return TradeResult(success=False, message=f"Symbol {symbol} not found")

        if not info.visible:
            mt5.symbol_select(symbol, True)

        spread_ok, spread_pts = self._check_spread(symbol)
        if not spread_ok:
            return TradeResult(
                success=False,
                message=f"Spread too high: {spread_pts:.0f} pts (max {self.cfg.symbol.spread_max:.0f})",
            )

        last_error_msg = ""
        for attempt in range(self._max_retries):
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                last_error_msg = "No tick data"
                time.sleep(self._retry_delay)
                continue

            if direction == "BUY":
                order_type = mt5.ORDER_TYPE_BUY
                price = tick.ask
            else:
                order_type = mt5.ORDER_TYPE_SELL
                price = tick.bid

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot_size,
                "type": order_type,
                "price": price,
                "sl": stop_loss,
                "tp": take_profit,
                "deviation": self.cfg.trade.slippage,
                "magic": self.cfg.trade.magic_number,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result is None:
                last_error_msg = f"order_send returned None: {mt5.last_error()}"
                logger.warning(f"Order attempt {attempt + 1}/{self._max_retries} failed: {last_error_msg}")
                time.sleep(self._retry_delay)
                continue

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"Order placed: {direction} {lot_size} lots @ {price}, ticket={result.order}")
                return TradeResult(
                    success=True,
                    ticket=result.order,
                    message=f"Trade executed: {direction} {lot_size} lots",
                    price=price,
                )

            last_error_msg = f"Order failed: {result.comment} (code {result.retcode})"
            logger.warning(f"Order attempt {attempt + 1}/{self._max_retries} failed: {last_error_msg}")
            time.sleep(self._retry_delay)

        return TradeResult(success=False, message=f"Order failed after {self._max_retries} retries: {last_error_msg}")

    def close_position(self, ticket: int, comment: str = "Close") -> TradeResult:
        if not self.connector or not self.connector.is_connected():
            return TradeResult(success=False, message="MT5 not connected")

        try:
            import MetaTrader5 as mt5
        except ImportError:
            return TradeResult(success=False, message="MetaTrader5 not installed")

        last_error_msg = ""
        for attempt in range(self._max_retries):
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return TradeResult(success=False, message=f"Position #{ticket} not found")

            pos = positions[0]
            symbol = pos.symbol
            volume = pos.volume

            if pos.type == mt5.ORDER_TYPE_BUY:
                order_type = mt5.ORDER_TYPE_SELL
                price = mt5.symbol_info_tick(symbol).bid
            else:
                order_type = mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(symbol).ask

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "position": ticket,
                "price": price,
                "deviation": self.cfg.trade.slippage,
                "magic": self.cfg.trade.magic_number,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"Position #{ticket} closed @ {price}")
                return TradeResult(success=True, ticket=ticket, message="Closed", price=price)

            last_error_msg = result.comment if result else "None"
            logger.warning(f"Close attempt {attempt + 1}/{self._max_retries} failed: {last_error_msg}")
            time.sleep(self._retry_delay)

        return TradeResult(success=False, message=f"Close failed after {self._max_retries} retries: {last_error_msg}")

    def modify_sl(self, ticket: int, new_sl: float) -> TradeResult:
        if not self.connector or not self.connector.is_connected():
            return TradeResult(success=False, message="MT5 not connected")

        try:
            import MetaTrader5 as mt5
        except ImportError:
            return TradeResult(success=False, message="MetaTrader5 not installed")

        last_error_msg = ""
        for attempt in range(self._max_retries):
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return TradeResult(success=False, message=f"Position #{ticket} not found")

            pos = positions[0]
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": pos.symbol,
                "position": ticket,
                "sl": new_sl,
                "tp": pos.tp,
            }

            result = mt5.order_send(request)
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"SL modified: #{ticket} -> {new_sl}")
                return TradeResult(success=True, ticket=ticket, message=f"SL moved to {new_sl}")

            last_error_msg = result.comment if result else "None"
            logger.warning(f"Modify attempt {attempt + 1}/{self._max_retries} failed: {last_error_msg}")
            time.sleep(self._retry_delay)

        return TradeResult(success=False, message=f"Modify failed after {self._max_retries} retries: {last_error_msg}")

    def set_break_even(self, ticket: int) -> TradeResult:
        if not self.cfg.trade.break_even_enabled:
            return TradeResult(success=False, message="Break even disabled")

        if not self.connector or not self.connector.is_connected():
            return TradeResult(success=False, message="MT5 not connected")

        try:
            import MetaTrader5 as mt5
        except ImportError:
            return TradeResult(success=False, message="MetaTrader5 not installed")

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return TradeResult(success=False, message=f"Position #{ticket} not found")

        pos = positions[0]
        entry = pos.price_open
        current_sl = pos.sl

        if pos.type == mt5.ORDER_TYPE_BUY:
            tick = mt5.symbol_info_tick(pos.symbol)
            if tick is None:
                return TradeResult(success=False, message="No tick")

            profit_pts = tick.bid - entry
            risk_pts = entry - current_sl if current_sl > 0 else 0

            if risk_pts <= 0:
                return TradeResult(success=False, message="No risk defined")

            if profit_pts >= risk_pts * self.cfg.trade.break_even_trigger_rr:
                new_sl = entry + self.cfg.symbol.point * 10
                return self.modify_sl(ticket, new_sl)

        else:
            tick = mt5.symbol_info_tick(pos.symbol)
            if tick is None:
                return TradeResult(success=False, message="No tick")

            profit_pts = entry - tick.ask
            risk_pts = current_sl - entry if current_sl > 0 else 0

            if risk_pts <= 0:
                return TradeResult(success=False, message="No risk defined")

            if profit_pts >= risk_pts * self.cfg.trade.break_even_trigger_rr:
                new_sl = entry - self.cfg.symbol.point * 10
                return self.modify_sl(ticket, new_sl)

        return TradeResult(success=False, message="BE trigger not reached")

    def trailing_stop(self, ticket: int, atr_value: float) -> TradeResult:
        if not self.cfg.trade.trailing_stop_enabled:
            return TradeResult(success=False, message="Trailing stop disabled")

        if not self.connector or not self.connector.is_connected():
            return TradeResult(success=False, message="MT5 not connected")

        try:
            import MetaTrader5 as mt5
        except ImportError:
            return TradeResult(success=False, message="MetaTrader5 not installed")

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return TradeResult(success=False, message=f"Position #{ticket} not found")

        pos = positions[0]
        entry = pos.price_open
        current_sl = pos.sl
        trail_distance = atr_value * self.cfg.trade.trailing_stop_distance_atr

        if pos.type == mt5.ORDER_TYPE_BUY:
            tick = mt5.symbol_info_tick(pos.symbol)
            if tick is None:
                return TradeResult(success=False, message="No tick")

            profit_pts = tick.bid - entry
            risk_pts = entry - current_sl if current_sl > 0 else 0

            if risk_pts > 0 and profit_pts >= risk_pts * self.cfg.trade.trailing_stop_trigger_rr:
                new_sl = tick.bid - trail_distance
                if new_sl > current_sl + self.cfg.symbol.point * 10:
                    return self.modify_sl(ticket, round(new_sl, 2))

        else:
            tick = mt5.symbol_info_tick(pos.symbol)
            if tick is None:
                return TradeResult(success=False, message="No tick")

            profit_pts = entry - tick.ask
            risk_pts = current_sl - entry if current_sl > 0 else 0

            if risk_pts > 0 and profit_pts >= risk_pts * self.cfg.trade.trailing_stop_trigger_rr:
                new_sl = tick.ask + trail_distance
                if new_sl < current_sl - self.cfg.symbol.point * 10 or current_sl == 0:
                    return self.modify_sl(ticket, round(new_sl, 2))

        return TradeResult(success=False, message="Trail not triggered")

    def partial_close(self, ticket: int, percent: Optional[float] = None) -> TradeResult:
        if not self.cfg.trade.partial_close_enabled:
            return TradeResult(success=False, message="Partial close disabled")

        try:
            import MetaTrader5 as mt5
        except ImportError:
            return TradeResult(success=False, message="MetaTrader5 not installed")

        close_pct = percent or self.cfg.trade.partial_close_percent
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return TradeResult(success=False, message=f"Position #{ticket} not found")

        pos = positions[0]
        close_volume = round(pos.volume * close_pct / 100, 2)

        if close_volume < self.cfg.risk.default_lot:
            return TradeResult(
                success=False,
                message=f"Partial close skipped: calculated {close_volume} lots < min {self.cfg.risk.default_lot}. Position is at minimum volume.",
            )

        close_volume = max(self.cfg.risk.default_lot, close_volume)

        if close_volume >= pos.volume:
            return TradeResult(
                success=False,
                message=f"Partial close skipped: close volume {close_volume} >= position volume {pos.volume}. Would close entire position.",
            )

        if pos.type == mt5.ORDER_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(pos.symbol).bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(pos.symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": close_volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": self.cfg.trade.slippage,
            "magic": self.cfg.trade.magic_number,
            "comment": f"Partial {close_pct}%",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            msg = result.comment if result else "None"
            return TradeResult(success=False, message=f"Partial close failed: {msg}")

        logger.info(f"Partial close #{ticket}: {close_volume} lots ({close_pct}%)")
        return TradeResult(success=True, ticket=ticket, message=f"Closed {close_volume} lots")

    def emergency_exit(self, reason: str = "Emergency") -> int:
        if not self.connector or not self.connector.is_connected():
            return 0

        positions = self.connector.get_positions()
        closed = 0
        for pos in positions:
            result = self.close_position(pos["ticket"], comment=f"EMERGENCY: {reason}")
            if result.success:
                closed += 1

        logger.warning(f"Emergency exit: closed {closed} positions ({reason})")
        return closed

    def manage_positions(self, atr_value: float = 0.0):
        if not self.connector or not self.connector.is_connected():
            return

        positions = self.connector.get_positions()
        for pos in positions:
            if pos.get("magic") != self.cfg.trade.magic_number:
                continue

            ticket = pos["ticket"]

            be_result = self.set_break_even(ticket)
            if be_result.success:
                logger.info(f"BE applied: #{ticket}")

            if atr_value > 0:
                trail_result = self.trailing_stop(ticket, atr_value)
                if trail_result.success:
                    logger.info(f"Trail applied: #{ticket}")
