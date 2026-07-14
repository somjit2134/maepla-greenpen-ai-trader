"""
MT5 Autonomous Trading System - Multi Timeframe Trend Engine
==============================================================
Analyzes trend alignment across timeframes:
  D1  -> Major market direction
  H4  -> Confirm market structure
  H1  -> Identify trading opportunity
  M15 -> Execute entry

BUY:  D1 bullish + H4 bullish + H1 bullish + M15 bullish
SELL: D1 bearish + H4 bearish + H1 bearish + M15 bearish
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from config import get_config

logger = logging.getLogger("trend_engine")


@dataclass
class TimeframeTrend:
    timeframe: str = ""
    bias: str = "NEUTRAL"
    condition: str = "RANGE"
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    sma20: float = 0.0
    detail: str = ""


@dataclass
class TrendResult:
    d1: TimeframeTrend = field(default_factory=TimeframeTrend)
    h4: TimeframeTrend = field(default_factory=TimeframeTrend)
    h1: TimeframeTrend = field(default_factory=TimeframeTrend)
    m15: TimeframeTrend = field(default_factory=TimeframeTrend)
    alignment_score: float = 0.0
    direction: str = "WAIT"
    is_tradeable: bool = False
    detail: str = ""


class TrendAnalyzer:
    """Multi-Timeframe Trend Engine."""

    def __init__(self):
        self.cfg = get_config()

    def analyze(self, data: dict[str, pd.DataFrame]) -> TrendResult:
        result = TrendResult()

        tf_data = {
            "D1": data.get("D1"),
            "H4": data.get("H4"),
            "H1": data.get("H1"),
            "M15": data.get("M15"),
        }

        for tf_key, analyzer in [("D1", "d1"), ("H4", "h4"), ("H1", "h1"), ("M15", "m15")]:
            df = tf_data.get(tf_key)
            if df is not None and not df.empty:
                trend = self._analyze_single(tf_key, df)
                setattr(result, analyzer, trend)

        result.alignment_score = self._calculate_alignment(result)
        result.direction = self._determine_direction(result)
        result.is_tradeable = result.alignment_score >= self.cfg.trend.min_alignment_score

        result.detail = (
            f"D1:{result.d1.bias} H4:{result.h4.bias} "
            f"H1:{result.h1.bias} M15:{result.m15.bias} "
            f"Score:{result.alignment_score:.1f} -> {result.direction}"
        )

        logger.info(f"Trend: {result.detail}")
        return result

    def _analyze_single(self, tf: str, df: pd.DataFrame) -> TimeframeTrend:
        if df.empty or len(df) < 30:
            return TimeframeTrend(timeframe=tf, detail="Insufficient data")

        close = df["close"].values
        ema12 = self._ema(close, 12)
        ema26 = self._ema(close, 26)
        sma20 = np.mean(close[-20:])

        current = close[-1]

        if ema12 > ema26 and current > sma20:
            bias = "BULLISH"
            condition = "BULLISH"
        elif ema12 < ema26 and current < sma20:
            bias = "BEARISH"
            condition = "BEARISH"
        else:
            bias = "NEUTRAL"
            condition = "RANGE"

        swing_high = df["high"].max()
        swing_low = df["low"].min()
        mid = (swing_high + swing_low) / 2

        if current > mid + (swing_high - mid) * 0.3:
            structure = "UPPER"
        elif current < mid - (mid - swing_low) * 0.3:
            structure = "LOWER"
        else:
            structure = "MIDDLE"

        return TimeframeTrend(
            timeframe=tf,
            bias=bias,
            condition=condition,
            ema_fast=round(ema12, 2),
            ema_slow=round(ema26, 2),
            sma20=round(sma20, 2),
            detail=f"Bias:{bias}, Structure:{structure}",
        )

    def _ema(self, data: np.ndarray, period: int) -> float:
        if len(data) < period:
            return float(np.mean(data))
        multiplier = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = (price - ema) * multiplier + ema
        return float(ema)

    def _calculate_alignment(self, result: TrendResult) -> float:
        score = 0.0
        weights = {
            "D1": self.cfg.trend.d1_weight,
            "H4": self.cfg.trend.h4_weight,
            "H1": self.cfg.trend.h1_weight,
            "M15": self.cfg.trend.m15_weight,
        }

        trends = {
            "D1": result.d1.bias,
            "H4": result.h4.bias,
            "H1": result.h1.bias,
            "M15": result.m15.bias,
        }

        bullish_count = sum(1 for b in trends.values() if b == "BULLISH")
        bearish_count = sum(1 for b in trends.values() if b == "BEARISH")

        if bullish_count >= 3:
            for tf, bias in trends.items():
                if bias == "BULLISH":
                    score += weights[tf]
        elif bearish_count >= 3:
            for tf, bias in trends.items():
                if bias == "BEARISH":
                    score += weights[tf]

        h4_bias = result.h4.bias
        d1_bias = result.d1.bias
        if h4_bias != "NEUTRAL" and h4_bias == d1_bias:
            score += 0.5

        return round(score, 1)

    def _determine_direction(self, result: TrendResult) -> str:
        bullish_count = sum(1 for t in [result.d1, result.h4, result.h1, result.m15]
                          if t.bias == "BULLISH")
        bearish_count = sum(1 for t in [result.d1, result.h4, result.h1, result.m15]
                          if t.bias == "BEARISH")

        if bullish_count >= 3 and result.alignment_score >= self.cfg.trend.min_alignment_score:
            return "BUY"
        elif bearish_count >= 3 and result.alignment_score >= self.cfg.trend.min_alignment_score:
            return "SELL"
        return "WAIT"
