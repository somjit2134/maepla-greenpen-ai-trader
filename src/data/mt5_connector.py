import time
from typing import Optional

import pandas as pd

from src.config_loader import get_config
from src.log_setup import get_logger

logger = get_logger()


class MT5Connector:
    """Handles MetaTrader 5 connection and data retrieval."""

    def __init__(self):
        self.cfg = get_config()
        self.initialized = False
        self.mt5 = None

    def connect(self) -> bool:
        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
        except ImportError:
            logger.error("MetaTrader5 package not installed. pip install MetaTrader5")
            return False

        if not self.mt5.initialize(
            path=self.cfg.mt5.path,
            login=self.cfg.mt5.login if self.cfg.mt5.login else None,
            password=self.cfg.mt5.password if self.cfg.mt5.password else None,
            server=self.cfg.mt5.server if self.cfg.mt5.server else None,
            timeout=self.cfg.mt5.timeout_seconds * 1000,
        ):
            err = self.mt5.last_error()
            logger.error(f"MT5 initialize failed: {err}")
            return False

        self.initialized = True
        logger.info("Connected to MetaTrader 5")
        return True

    def disconnect(self):
        if self.mt5 and self.initialized:
            self.mt5.shutdown()
            self.initialized = False
            logger.info("Disconnected from MetaTrader 5")

    def is_connected(self) -> bool:
        return self.initialized and (self.mt5 is not None)

    def get_rates(
        self,
        timeframe: str,
        count: int = 500,
    ) -> pd.DataFrame:
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

        rates = self.mt5.copy_rates_from_pos(
            self.cfg.symbol.name, mt5_tf, 0, count
        )
        if rates is None:
            err = self.mt5.last_error()
            logger.error(f"Failed to get rates for {timeframe}: {err}")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def get_current_price(self) -> tuple[float, float]:
        tick = self.mt5.symbol_info_tick(self.cfg.symbol.name)
        if tick is None:
            return 0.0, 0.0
        return tick.bid, tick.ask

    def get_account_info(self) -> Optional[dict]:
        info = self.mt5.account_info()
        if info is None:
            return None
        return {
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "margin_free": info.margin_free,
            "profit": info.profit,
            "leverage": info.leverage,
        }

    def get_all_timeframes(self, count: int = 500) -> dict[str, pd.DataFrame]:
        tfs = ["M1", "M5", "M15", "H1", "H4", "D1", "W1", "MN1"]
        result = {}
        for tf in tfs:
            df = self.get_rates(tf, count)
            if not df.empty:
                result[tf] = df
        return result


class SimulatedMT5Connector:
    """Simulated connector for testing / demo mode when MT5 is not available."""

    import numpy as np

    def __init__(self):
        self.cfg = get_config()
        self.initialized = True
        self._base_price = self.cfg.symbol.at * 0.73

    def connect(self) -> bool:
        logger.info("Using simulated MT5 connector (no live data)")
        return True

    def disconnect(self):
        pass

    def is_connected(self) -> bool:
        return True

    def get_rates(self, timeframe: str, count: int = 500) -> pd.DataFrame:
        import numpy as np
        import pandas as pd

        now = pd.Timestamp.now(tz=None)
        tf_minutes = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440, "W1": 10080, "MN1": 43200}
        step = tf_minutes.get(timeframe, 60)

        times = [now - pd.Timedelta(minutes=step * (count - i)) for i in range(count)]
        np.random.seed(42)
        noise = np.random.randn(count) * 5
        trend = np.linspace(0, -self._base_price * 0.05, count)
        prices = self._base_price + trend + noise.cumsum()

        df = pd.DataFrame({
            "time": times,
            "open": prices + np.random.randn(count) * 2,
            "high": prices + np.abs(np.random.randn(count)) * 5 + 3,
            "low": prices - np.abs(np.random.randn(count)) * 5 - 3,
            "close": prices,
            "tick_volume": np.random.randint(100, 5000, count),
            "spread": np.random.randint(10, 50, count),
            "real_volume": np.random.randint(1000, 50000, count),
        })
        return df

    def get_current_price(self) -> tuple[float, float]:
        import numpy as np
        price = self._base_price + np.random.randn() * 3
        return price, price + 0.5

    def get_account_info(self) -> dict:
        return {"balance": 10000, "equity": 10000, "margin": 0, "margin_free": 10000, "profit": 0, "leverage": 100}

    def get_all_timeframes(self, count: int = 500) -> dict[str, pd.DataFrame]:
        tfs = ["M1", "M5", "M15", "H1", "H4", "D1", "W1", "MN1"]
        return {tf: self.get_rates(tf, count) for tf in tfs}
