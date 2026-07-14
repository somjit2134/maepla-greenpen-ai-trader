import time
from typing import Optional

import pandas as pd
import numpy as np

from src.config import get
from src.logger import get_logger

logger = get_logger()

_instance: Optional["MT5Connector"] = None


def get_connector() -> "MT5Connector":
    global _instance
    if _instance is None:
        _instance = MT5Connector()
    return _instance


class MT5Connector:
    def __init__(self):
        self.cfg = get()
        self.mt5 = None
        self.initialized = False

    def connect(self) -> bool:
        if self.initialized and self.mt5 is not None:
            logger.debug("Already connected to MT5, skipping initialize")
            return True

        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
        except ImportError:
            logger.error("MetaTrader5 package not installed")
            return False

        kw = {"path": self.cfg.mt5.path, "timeout": self.cfg.mt5.timeout_seconds * 1000}
        if self.cfg.mt5.login:
            kw["login"] = self.cfg.mt5.login
            kw["password"] = self.cfg.mt5.password
            kw["server"] = self.cfg.mt5.server

        if not self.mt5.initialize(**kw):
            err = self.mt5.last_error()
            logger.error(f"MT5 init failed: {err}")
            return False

        self.initialized = True
        self._log_diagnostics()
        logger.info(f"Connected to MT5 | {self.cfg.symbol.name}")
        return True

    def _log_diagnostics(self):
        if self.mt5 is None:
            return
        try:
            ti = self.mt5.terminal_info()
            if ti:
                logger.info(
                    f"[DIAG] terminal: name={ti.name} build={ti.build} "
                    f"connected={ti.connected} trade_allowed={ti.trade_allowed} "
                    f"tradeapi_disabled={ti.tradeapi_disabled} "
                    f"community_account={ti.community_account}"
                )
            else:
                logger.warning("[DIAG] terminal_info() returned None")
        except Exception as e:
            logger.warning(f"[DIAG] terminal_info error: {e}")

        try:
            ai = self.mt5.account_info()
            if ai:
                logger.info(
                    f"[DIAG] account: login={ai.login} server={ai.server} "
                    f"balance={ai.balance} equity={ai.equity} "
                    f"margin_free={ai.margin_free} leverage={ai.leverage} "
                    f"trade_allowed={ai.trade_allowed}"
                )
            else:
                logger.warning("[DIAG] account_info() returned None")
        except Exception as e:
            logger.warning(f"[DIAG] account_info error: {e}")

    def ensure_connected(self) -> bool:
        if self.initialized and self.mt5 is not None:
            try:
                ti = self.mt5.terminal_info()
                if ti and ti.connected:
                    return True
            except Exception:
                pass
        logger.warning("MT5 connection lost, reconnecting...")
        self.initialized = False
        return self.connect()

    def disconnect(self):
        global _instance
        if self.mt5 and self.initialized:
            self.mt5.shutdown()
            self.initialized = False
        _instance = None

    @property
    def connected(self) -> bool:
        return self.initialized and self.mt5 is not None

    TF_MAP = {
        "M1": 1, "M5": 5, "M15": 15, "M30": 30,
        "H1": 16385, "H4": 16388, "D1": 16408, "W1": 16410, "MN1": 16413,
    }

    def _tf(self, name: str):
        return self.TF_MAP.get(name, 16388)

    def rates(self, timeframe: str, count: int = 500) -> pd.DataFrame:
        tf = self._tf(timeframe)
        arr = self.mt5.copy_rates_from_pos(self.cfg.symbol.name, tf, 0, count)
        if arr is None:
            logger.error(f"Failed rates {timeframe}: {self.mt5.last_error()}")
            return pd.DataFrame()
        df = pd.DataFrame(arr)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def tick(self) -> tuple[float, float, float]:
        t = self.mt5.symbol_info_tick(self.cfg.symbol.name)
        if t is None:
            return 0.0, 0.0, 0.0
        return t.bid, t.ask, (t.ask - t.bid)

    def account(self) -> dict:
        i = self.mt5.account_info()
        if i is None:
            return {}
        return {"balance": i.balance, "equity": i.equity, "margin_free": i.margin_free,
                "profit": i.profit, "leverage": i.leverage}

    def all_rates(self, count: int = 300) -> dict[str, pd.DataFrame]:
        return {tf: self.rates(tf, count) for tf in ("M1", "M15", "H1", "H4", "D1", "W1", "MN1") if self.rates(tf, count).shape[0] > 0}

    def get_symbol_filling(self) -> int:
        info = self.mt5.symbol_info(self.cfg.symbol.name)
        if info is None:
            logger.warning(f"Cannot get symbol info for {self.cfg.symbol.name}, defaulting to FOK")
            return self.mt5.ORDER_FILLING_FOK
        mode = info.filling_mode
        logger.info(f"Symbol filling_mode={mode} (FOK={bool(mode & 1)}, IOC={bool(mode & 2)})")
        if mode & 2:
            return self.mt5.ORDER_FILLING_IOC
        elif mode & 1:
            return self.mt5.ORDER_FILLING_FOK
        else:
            return self.mt5.ORDER_FILLING_RETURN

    def pre_order_check(self) -> tuple[bool, str]:
        if not self.ensure_connected():
            return False, "MT5 not connected"

        ti = self.mt5.terminal_info()
        if ti is None:
            return False, "terminal_info() returned None"

        if not ti.connected:
            return False, "terminal not connected to broker"

        if not ti.trade_allowed:
            logger.warning(
                f"[PRE-CHECK] trade_allowed={ti.trade_allowed} "
                f"tradeapi_disabled={ti.tradeapi_disabled}"
            )
            return False, "AutoTrading is disabled in MT5 terminal (enable the button or Ctrl+E)"

        if ti.tradeapi_disabled:
            return False, "Trade API is disabled in MT5 settings"

        ai = self.mt5.account_info()
        if ai is None:
            return False, "account_info() returned None"

        if not ai.trade_allowed:
            return False, "Trading is not allowed on this account"

        return True, "ok"

    def order_send(self, request: dict) -> Optional[dict]:
        ok, reason = self.pre_order_check()
        if not ok:
            logger.error(f"[PRE-CHECK FAILED] {reason}")
            return {"retcode": -1, "ticket": 0, "comment": reason,
                    "volume": 0, "price": 0, "sl": 0, "tp": 0}

        r = self.mt5.order_send(request)
        if r is None:
            err = self.mt5.last_error()
            logger.error(f"Order send failed: {err}")
            return {"retcode": -1, "ticket": 0, "comment": str(err),
                    "volume": 0, "price": 0, "sl": 0, "tp": 0}

        result = {"retcode": r.retcode, "ticket": r.order, "comment": getattr(r, 'comment', ''),
                  "volume": getattr(r, 'volume', 0), "price": getattr(r, 'price', 0),
                  "sl": getattr(r, 'sl', 0), "tp": getattr(r, 'tp', 0)}

        if r.retcode != 10009 and r.retcode != 0:
            logger.error(f"Order failed retcode={r.retcode} comment={r.comment}")
            ti = self.mt5.terminal_info()
            if ti:
                logger.error(
                    f"[POST-FAIL DIAG] trade_allowed={ti.trade_allowed} "
                    f"tradeapi_disabled={ti.tradeapi_disabled} connected={ti.connected}"
                )

        return result

    def positions(self) -> list[dict]:
        ps = self.mt5.positions_get(symbol=self.cfg.symbol.name) or []
        return [{"ticket": p.ticket, "type": "BUY" if p.type == 0 else "SELL",
                 "volume": p.volume, "price": p.price_open, "sl": p.sl, "tp": p.tp,
                 "profit": p.profit, "swap": p.swap} for p in ps]


class SimConnector:
    def __init__(self):
        self.cfg = get()
        self.initialized = True
        self._base = self.cfg.symbol.at * 0.73

    def connect(self) -> bool:
        logger.info("Simulated connector active")
        return True

    def disconnect(self):
        pass

    @property
    def connected(self) -> bool:
        return True

    def ensure_connected(self) -> bool:
        return True

    def pre_order_check(self) -> tuple[bool, str]:
        return True, "ok"

    def rates(self, timeframe: str, count: int = 500) -> pd.DataFrame:
        tf_min = {"M1": 1, "M15": 15, "H1": 60, "H4": 240, "D1": 1440, "W1": 10080, "MN1": 43200}
        step = tf_min.get(timeframe, 60)
        now = pd.Timestamp.now()
        times = [now - pd.Timedelta(minutes=step * (count - i)) for i in range(count)]

        np.random.seed(42)
        trend = np.linspace(0, -self._base * 0.06, count)
        noise = np.random.randn(count).cumsum() * 3
        prices = self._base + trend + noise

        return pd.DataFrame({
            "time": times,
            "open": prices + np.random.randn(count) * 2,
            "high": prices + np.abs(np.random.randn(count)) * 6 + 4,
            "low": prices - np.abs(np.random.randn(count)) * 6 - 4,
            "close": prices,
            "tick_volume": np.random.randint(100, 5000, count),
            "spread": np.random.randint(15, 45, count),
            "real_volume": np.random.randint(1000, 50000, count),
        })

    def tick(self) -> tuple[float, float, float]:
        p = self._base + np.random.randn() * 3
        return p, p + 0.4, 0.4

    def account(self) -> dict:
        return {"balance": 10000, "equity": 10000, "margin_free": 9500, "profit": 0, "leverage": 100}

    def all_rates(self, count: int = 300) -> dict[str, pd.DataFrame]:
        return {tf: self.rates(tf, count) for tf in ("M1", "M15", "H1", "H4", "D1", "W1", "MN1")}

    def get_symbol_filling(self) -> int:
        return 0

    def order_send(self, request: dict) -> dict:
        logger.info(f"[SIM] Order: {request.get('type')} {request.get('volume')} lots")
        return {"retcode": 10009, "ticket": 10000 + np.random.randint(1, 9999),
                "comment": "Simulated", "volume": request.get("volume", 0.01),
                "price": request.get("price", 0), "sl": request.get("sl", 0), "tp": request.get("tp", 0)}

    def positions(self) -> list[dict]:
        return []
