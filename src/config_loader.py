import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


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


@dataclass
class AnalysisConfig:
    update_interval_seconds: int = 60
    enable_notifications: bool = True
    enable_auto_trading: bool = False


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/trader.log"


@dataclass
class Config:
    mt5: MT5Config = field(default_factory=MT5Config)
    symbol: SymbolConfig = field(default_factory=SymbolConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    line_notify: LineNotifyConfig = field(default_factory=LineNotifyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


_config_instance: Optional[Config] = None


def load_config(path: Optional[str] = None) -> Config:
    global _config_instance

    if path is None:
        base = Path(__file__).parent.parent
        path = str(base / "config" / "config.yaml")

    cfg = Config()

    if os.path.exists(path):
        with open(path, "r") as f:
            raw = yaml.safe_load(f) or {}

        if "mt5" in raw:
            for k, v in raw["mt5"].items():
                if hasattr(cfg.mt5, k):
                    setattr(cfg.mt5, k, v)
        if "symbol" in raw:
            for k, v in raw["symbol"].items():
                if hasattr(cfg.symbol, k):
                    setattr(cfg.symbol, k, v)
        if "database" in raw:
            for k, v in raw["database"].items():
                if hasattr(cfg.database, k):
                    setattr(cfg.database, k, v)
        if "line_notify" in raw:
            for k, v in raw["line_notify"].items():
                if hasattr(cfg.line_notify, k):
                    setattr(cfg.line_notify, k, v)
        if "risk" in raw:
            for k, v in raw["risk"].items():
                if hasattr(cfg.risk, k):
                    setattr(cfg.risk, k, v)
        if "analysis" in raw:
            for k, v in raw["analysis"].items():
                if hasattr(cfg.analysis, k):
                    setattr(cfg.analysis, k, v)
        if "logging" in raw:
            for k, v in raw["logging"].items():
                if hasattr(cfg.logging, k):
                    setattr(cfg.logging, k, v)

    _config_instance = cfg
    return cfg


def get_config() -> Config:
    global _config_instance
    if _config_instance is None:
        return load_config()
    return _config_instance
