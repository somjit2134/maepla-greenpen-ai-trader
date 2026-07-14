"""
MT5 Autonomous Trading System - MetaTrader 5 Connection
=========================================================
Handles connection, data retrieval, and auto-reconnect.
"""
import time
import logging
from typing import Optional

import pandas as pd
import numpy as np

from config import get_config

logger = logging.getLogger("mt5_connector")


class MT5Connector:
    """Handles MetaTrader 5 connection with auto-reconnect."""

    def __init__(self):
        self.cfg = get_config()
        self.mt5 = None
        self.connected = False

    def connect(self) -> bool:
        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
        except ImportError:
            logger.error("MetaTrader5 not installed. Run: pip install MetaTrader5")
            return False

        kwargs = {"path": self.cfg.mt5.path, "timeout": self.cfg.mt5.timeout_seconds * 1000}
        if self.cfg.mt5.login:
            kwargs["login"] = self.cfg.mt5.login
            kwargs["password"] = self.cfg.mt5.password or ""
            kwargs["server"] = self.cfg.mt5.server or ""

        if not self.mt5.initialize(**kwargs):
            err = self.mt5.last_error()
            logger.error(f"MT5 initialize failed: {err}")
            return False

        self.connected = True
        logger.info("Connected to MetaTrader 5")
        return True

    def reconnect(self) -> bool:
        """Attempt to reconnect with retry logic."""
        for attempt in range(self.cfg.mt5.reconnect_attempts):
            logger.warning(f"Reconnect attempt {attempt + 1}/{self.cfg.mt5.reconnect_attempts}")
            self.disconnect()
            time.sleep(self.cfg.mt5.reconnect_delay_seconds)
            if self.connect():
                logger.info("Reconnected successfully")
                return True
        logger.error("Failed to reconnect after all attempts")
        return False

    def disconnect(self):
        if self.mt5:
            try:
                self.mt5.shutdown()
            except Exception:
                pass
        self.connected = False
        logger.info("Disconnected from MetaTrader 5")

    def is_connected(self) -> bool:
        if not self.connected or self.mt5 is None:
            return False
        try:
            info = self.mt5.terminal_info()
            return info is not None and info.connected
        except Exception:
            self.connected = False
            return False

    def ensure_connected(self) -> bool:
        """Check connection, reconnect if needed."""
        if self.is_connected():
            return True
        logger.warning("MT5 disconnected, attempting reconnect...")
        return self.reconnect()

    def get_rates(self, timeframe: str, count: int = 500) -> pd.DataFrame:
        if not self.ensure_connected():
            return pd.DataFrame()

        tf_map = {
            "M1": self.mt5.TIMEFRAME_M1,
            "M5": self.mt5.TIMEFRAME_M5,
            "M15": self.mt5.TIMEFRAME_M15,
            "H1": self.mt5.TIMEFRAME_H1,
            "H4": self.mt5.TIMEFRAME_H4,
            "D1": self.mt5.TIMEFRAME_D1,
            "W1": self.mt5.TIMEFRAME_W1,
            "MN1": self.mt5.TIMEFRAME_MN1,
        }

        mt5_tf = tf_map.get(timeframe)
        if mt5_tf is None:
            logger.error(f"Unknown timeframe: {timeframe}")
            return pd.DataFrame()

        rates = self.mt5.copy_rates_from_pos(self.cfg.symbol.name, mt5_tf, 0, count)
        if rates is None or len(rates) == 0:
            logger.error(f"Failed to get {timeframe} data: {self.mt5.last_error()}")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def get_current_price(self) -> tuple[float, float]:
        """Returns (bid, ask)."""
        if not self.ensure_connected():
            return 0.0, 0.0

        tick = self.mt5.symbol_info_tick(self.cfg.symbol.name)
        if tick is None:
            return 0.0, 0.0
        return tick.bid, tick.ask

    def get_spread(self) -> float:
        """Current spread in points."""
        bid, ask = self.get_current_price()
        return (ask - bid) / self.cfg.symbol.point if bid > 0 else 0.0

    def get_account_info(self) -> Optional[dict]:
        if not self.ensure_connected():
            return None

        info = self.mt5.account_info()
        if info is None:
            return None
        return {
            "login": info.login,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "margin_free": info.margin_free,
            "profit": info.profit,
            "leverage": info.leverage,
            "server": info.server,
        }

    def get_symbol_info(self) -> Optional[dict]:
        if not self.ensure_connected():
            return None

        info = self.mt5.symbol_info(self.cfg.symbol.name)
        if info is None:
            return None
        return {
            "name": info.name,
            "point": info.point,
            "digits": info.digits,
            "spread": info.spread,
            "trade_mode": info.trade_mode,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
        }

    def get_all_timeframes(self, count: int = 500) -> dict[str, pd.DataFrame]:
        tfs = ["M15", "H1", "H4", "D1", "W1", "MN1"]
        result = {}
        for tf in tfs:
            df = self.get_rates(tf, count)
            if not df.empty:
                result[tf] = df
        return result

    def get_positions(self) -> list[dict]:
        if not self.ensure_connected():
            return []

        positions = self.mt5.positions_get(symbol=self.cfg.symbol.name)
        if not positions:
            return []

        return [
            {
                "ticket": p.ticket,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "price_current": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "swap": p.swap,
                "magic": p.magic,
                "comment": p.comment,
                "time": p.time,
            }
            for p in positions
        ]

    def get_history_orders(self, days: int = 30) -> list[dict]:
        if not self.ensure_connected():
            return []

        from datetime import datetime, timedelta
        date_from = datetime.now() - timedelta(days=days)
        date_to = datetime.now()

        deals = self.mt5.history_deals_get(date_from, date_to, group=f"*{self.cfg.symbol.name}*")
        if not deals:
            return []

        return [
            {
                "ticket": d.ticket,
                "order": d.order,
                "position_id": d.position_id,
                "time": d.time,
                "type": d.type,
                "entry": d.entry,
                "volume": d.volume,
                "price": d.price,
                "profit": d.profit,
                "swap": d.swap,
                "commission": d.commission,
                "comment": d.comment,
                "magic": d.magic,
            }
            for d in deals
        ]
