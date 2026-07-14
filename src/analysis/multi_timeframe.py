from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from src.analysis.market_structure import MarketStructureDetector, MarketStructure
from src.analysis.support_resistance import SupportResistanceDetector, SRResult
from src.log_setup import get_logger

logger = get_logger()


@dataclass
class TimeframeResult:
    timeframe: str = ""
    bias: str = "NEUTRAL"
    structure: Optional[MarketStructure] = None
    sr: Optional[SRResult] = None
    current_price: float = 0.0
    swing_high: float = 0.0
    swing_low: float = 0.0
    detail: str = ""


@dataclass
class MultiTimeframeResult:
    monthly: Optional[TimeframeResult] = None
    weekly: Optional[TimeframeResult] = None
    daily: Optional[TimeframeResult] = None
    h4: Optional[TimeframeResult] = None
    h1: Optional[TimeframeResult] = None
    m15: Optional[TimeframeResult] = None

    monthly_bias: str = "NEUTRAL"
    weekly_bias: str = "NEUTRAL"
    daily_zone: str = ""
    h4_structure: str = "RANGE"
    h1_direction: str = "NEUTRAL"
    h4_bias: str = "WAIT"

    support_zones: list = field(default_factory=list)
    resistance_zones: list = field(default_factory=list)


class MultiTimeframeAnalyzer:
    def __init__(self):
        self.structure_detector = MarketStructureDetector()
        self.sr_detector = SupportResistanceDetector(cluster_distance=5.0)

    def _analyze_single(self, tf: str, df: pd.DataFrame) -> TimeframeResult:
        if df.empty:
            return TimeframeResult(timeframe=tf, detail="No data")

        close = df["close"].values
        current_price = close[-1]
        swing_high = df["high"].max()
        swing_low = df["low"].min()

        structure = self.structure_detector.detect(df)
        sr = self.sr_detector.detect(df)

        bias = "NEUTRAL"
        if structure.condition == "BULLISH":
            bias = "BULLISH"
        elif structure.condition == "BEARISH":
            bias = "BEARISH"

        result = TimeframeResult(
            timeframe=tf,
            bias=bias,
            structure=structure,
            sr=sr,
            current_price=current_price,
            swing_high=swing_high,
            swing_low=swing_low,
            detail=f"Bias: {bias}, Structure: {structure.condition}",
        )
        return result

    def analyze(self, data: dict[str, pd.DataFrame]) -> MultiTimeframeResult:
        result = MultiTimeframeResult()

        if "MN1" in data:
            result.monthly = self._analyze_single("MN1", data["MN1"])
            result.monthly_bias = result.monthly.bias

        if "W1" in data:
            result.weekly = self._analyze_single("W1", data["W1"])
            result.weekly_bias = result.weekly.bias

        if "D1" in data:
            result.daily = self._analyze_single("D1", data["D1"])
            sr = result.daily.sr
            if sr:
                price = result.daily.current_price
                res = [f"${r.mid:.2f}" for r in sr.resistances[:3] if r.mid > price]
                sup = [f"${s.mid:.2f}" for s in sr.supports[:3] if s.mid < price]
                result.daily_zone = f"Sup: {', '.join(sup[:2])} | Res: {', '.join(res[:2])}"
                result.support_zones = sup[:3]
                result.resistance_zones = res[:3]

        if "H4" in data:
            result.h4 = self._analyze_single("H4", data["H4"])
            result.h4_structure = result.h4.structure.condition if result.h4.structure else "RANGE"
            if result.h4_structure == "BULLISH":
                result.h4_bias = "BUY ONLY"
            elif result.h4_structure == "BEARISH":
                result.h4_bias = "SELL ONLY"
            else:
                result.h4_bias = "WAIT"

        if "H1" in data:
            result.h1 = self._analyze_single("H1", data["H1"])
            result.h1_direction = result.h1.bias

        if "M15" in data:
            result.m15 = self._analyze_single("M15", data["M15"])

        logger.info(
            f"MTF Analysis: Monthly={result.monthly_bias}, "
            f"H4={result.h4_bias}, H1={result.h1_direction}"
        )
        return result
