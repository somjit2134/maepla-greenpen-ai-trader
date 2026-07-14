import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class MT5Config:
    path: str = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
    login: int = 0
    password: str = ""
    server: str = ""
    timeout_seconds: int = 30


@dataclass
class SymbolConfig:
    name: str = "XAUUSD"
    at: float = 5603.0
    digit: int = 2
    min_volume: float = 0.01
    max_volume: float = 10.0
    volume_step: float = 0.01


@dataclass
class DatabaseConfig:
    path: str = "data/trading.db"


@dataclass
class LineNotifyConfig:
    token: str = ""
    enabled: bool = False


@dataclass
class RiskConfig:
    default_risk_percent: float = 1.0
    max_risk_percent: float = 2.0
    min_rr: float = 2.0
    max_daily_loss_percent: float = 5.0
    max_open_trades: int = 1
    max_spread: int = 50
    slippage: int = 20


@dataclass
class TradingConfig:
    auto_trade: bool = False
    execute_score_threshold: int = 9
    alert_score_threshold: int = 7
    monitor_interval_seconds: int = 60
    enable_monitoring: bool = True


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/autotrader.log"


@dataclass
class Config:
    mt5: MT5Config = field(default_factory=MT5Config)
    symbol: SymbolConfig = field(default_factory=SymbolConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    line_notify: LineNotifyConfig = field(default_factory=LineNotifyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


_instance: Optional[Config] = None


def load(path: str | None = None) -> Config:
    global _instance
    if path is None:
        path = str(Path(__file__).parent.parent / "config" / "config.yaml")

    cfg = Config()

    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        for section, obj in [
            ("mt5", cfg.mt5),
            ("symbol", cfg.symbol),
            ("database", cfg.database),
            ("line_notify", cfg.line_notify),
            ("risk", cfg.risk),
            ("trading", cfg.trading),
            ("logging", cfg.logging),
        ]:
            if section in raw:
                for k, v in raw[section].items():
                    if hasattr(obj, k):
                        setattr(obj, k, v)

    _instance = cfg
    return cfg


def get() -> Config:
    global _instance
    if _instance is None:
        return load()
    return _instance
