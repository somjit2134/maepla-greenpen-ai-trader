"""
MT5 Autonomous Trading System - Configuration
===============================================
Central config for all engines: MT5, Frame, Cycle, Trend, PA, Risk, Trade, Backtest.
"""
import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class MT5Config:
    path: str = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
    login: int = int(os.getenv("MT5_LOGIN", "0"))
    password: str = os.getenv("MT5_PASSWORD", "")
    server: str = os.getenv("MT5_SERVER", "")
    timeout_seconds: int = 30
    reconnect_attempts: int = 5
    reconnect_delay_seconds: int = 5


@dataclass
class SymbolConfig:
    name: str = "XAUUSD"
    digit: int = 2
    point: float = 0.01
    contract_size: float = 100.0
    spread_max: float = 50.0
    at: float = 5603.0


@dataclass
class FrameConfig:
    ath_caution_percent: float = 5.0
    sideway_range_percent: float = 2.0
    sideway_min_bars: int = 20
    important_zone_step: float = 50.0


@dataclass
class CycleConfig:
    lookback_bars: int = 100
    early_threshold: float = 30.0
    late_threshold: float = 70.0
    exhaustion_rsi_period: int = 14


@dataclass
class TrendConfig:
    d1_weight: float = 1.0
    h4_weight: float = 1.0
    h1_weight: float = 0.5
    m15_weight: float = 0.5
    min_alignment_score: float = 3.0


@dataclass
class PriceActionConfig:
    pin_bar_body_ratio: float = 0.3
    pin_bar_wick_ratio: float = 0.5
    engulfing_min_body: float = 0.5
    false_breakout_bars: int = 3


@dataclass
class RiskConfig:
    risk_per_trade_percent: float = 1.0
    max_risk_percent: float = 2.0
    max_daily_loss_percent: float = 5.0
    max_open_positions: int = 3
    max_consecutive_losses: int = 3
    min_rr: float = 2.0
    default_lot: float = 0.01
    max_lot: float = 10.0


@dataclass
class TradeConfig:
    break_even_enabled: bool = True
    break_even_trigger_rr: float = 1.5
    trailing_stop_enabled: bool = True
    trailing_stop_trigger_rr: float = 2.0
    trailing_stop_distance_atr: float = 1.5
    partial_close_enabled: bool = True
    partial_close_percent: float = 50.0
    partial_close_at_tp1: bool = True
    magic_number: int = 20260712
    slippage: int = 20


@dataclass
class BacktestConfig:
    initial_balance: float = 10000.0
    commission_per_lot: float = 7.0
    monte_carlo_runs: int = 1000
    walk_forward_splits: int = 5


@dataclass
class DatabaseConfig:
    path: str = "data/trading.db"
    backtest_path: str = "data/backtest.db"


@dataclass
class NotificationConfig:
    line_notify_token: str = ""
    line_notify_enabled: bool = False


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/trader.log"


@dataclass
class Config:
    mt5: MT5Config = field(default_factory=MT5Config)
    symbol: SymbolConfig = field(default_factory=SymbolConfig)
    frame: FrameConfig = field(default_factory=FrameConfig)
    cycle: CycleConfig = field(default_factory=CycleConfig)
    trend: TrendConfig = field(default_factory=TrendConfig)
    price_action: PriceActionConfig = field(default_factory=PriceActionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    trade: TradeConfig = field(default_factory=TradeConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


_config: Optional[Config] = None


def load_config(path: Optional[str] = None) -> Config:
    global _config

    load_dotenv()

    if path is None:
        base = Path(__file__).parent.parent
        path = str(base / "config.yaml")

    cfg = Config()

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        section_map = {
            "mt5": (cfg.mt5, MT5Config),
            "symbol": (cfg.symbol, SymbolConfig),
            "frame": (cfg.frame, FrameConfig),
            "cycle": (cfg.cycle, CycleConfig),
            "trend": (cfg.trend, TrendConfig),
            "price_action": (cfg.price_action, PriceActionConfig),
            "risk": (cfg.risk, RiskConfig),
            "trade": (cfg.trade, TradeConfig),
            "backtest": (cfg.backtest, BacktestConfig),
            "database": (cfg.database, DatabaseConfig),
            "notification": (cfg.notification, NotificationConfig),
            "logging": (cfg.logging, LoggingConfig),
        }

        for section_name, (obj, _) in section_map.items():
            if section_name in raw:
                for k, v in raw[section_name].items():
                    if hasattr(obj, k):
                        setattr(obj, k, v)

    env_login = os.getenv("MT5_LOGIN")
    if env_login:
        cfg.mt5.login = int(env_login)
    env_password = os.getenv("MT5_PASSWORD")
    if env_password is not None:
        cfg.mt5.password = env_password
    env_server = os.getenv("MT5_SERVER")
    if env_server is not None:
        cfg.mt5.server = env_server

    _config = cfg
    return cfg


def get_config() -> Config:
    global _config
    if _config is None:
        return load_config()
    return _config
