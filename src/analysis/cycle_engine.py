"""
MT5 Autonomous Trading System - Cycle Analysis Engine
======================================================
Measures price movement cycles:
  - Distance from previous swing
  - Remaining potential movement
  - EARLY / MIDDLE / LATE classification
  - Exhaustion detection (RSI divergence)
"""
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from src.config import get_config

logger = logging.getLogger("cycle_engine")


@dataclass
class CycleResult:
    swing_high: float = 0.0
    swing_low: float = 0.0
    cycle_start: float = 0.0
    cycle_end: float = 0.0
    total_distance: float = 0.0
    current_distance: float = 0.0
    progress_percent: float = 0.0
    position: str = "MIDDLE"
    remaining_potential: float = 0.0
    exhaustion_risk: bool = False
    rsi_value: float = 50.0
    detail: str = ""


class CycleAnalyzer:
    """Cycle Analysis Engine - measure position in price cycle."""

    def __init__(self):
        self.cfg = get_config()

    def analyze(self, data: dict[str, pd.DataFrame], current_price: float) -> CycleResult:
        h4 = data.get("H4")
        d1 = data.get("D1")

        df = d1 if d1 is not None and not d1.empty else h4
        if df is None or df.empty:
            return CycleResult(detail="No data available")

        result = self._find_cycle(current_price, df)
        result.rsi_value = self._calculate_rsi(df)
        result.exhaustion_risk = self._detect_exhaustion(result, df)

        logger.info(f"Cycle: {result.position} ({result.progress_percent:.0f}%), "
                     f"Remaining: {result.remaining_potential:.0f}pts, "
                     f"Exhaustion: {result.exhaustion_risk}")
        return result

    def _find_cycle(self, price: float, df: pd.DataFrame) -> CycleResult:
        lookback = min(self.cfg.cycle.lookback_bars, len(df))
        recent = df.tail(lookback)

        swing_high = recent["high"].max()
        swing_low = recent["low"].min()
        total_distance = swing_high - swing_low

        if total_distance <= 0:
            return CycleResult(detail="No cycle range")

        high_idx = recent["high"].idxmax()
        low_idx = recent["low"].idxmin()

        if high_idx > low_idx:
            cycle_start = swing_low
            cycle_end = swing_high
        else:
            cycle_start = swing_high
            cycle_end = swing_low

        current_distance = price - swing_low
        progress = (current_distance / total_distance) * 100
        progress = max(0, min(100, progress))

        if progress < self.cfg.cycle.early_threshold:
            position = "EARLY"
        elif progress < self.cfg.cycle.late_threshold:
            position = "MIDDLE"
        else:
            position = "LATE"

        remaining = swing_high - price if high_idx > low_idx else price - swing_low
        remaining = max(0, remaining)

        return CycleResult(
            swing_high=swing_high,
            swing_low=swing_low,
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            total_distance=round(total_distance, 2),
            current_distance=round(current_distance, 2),
            progress_percent=round(progress, 1),
            position=position,
            remaining_potential=round(remaining, 2),
            detail=f"{position} cycle at {progress:.0f}%, {remaining:.0f}pts remaining",
        )

    def _calculate_rsi(self, df: pd.DataFrame, period: Optional[int] = None) -> float:
        period = period or self.cfg.cycle.exhaustion_rsi_period
        if len(df) < period + 1:
            return 50.0

        close = df["close"].values
        deltas = np.diff(close[-(period + 1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)

    def _detect_exhaustion(self, cycle: CycleResult, df: pd.DataFrame) -> bool:
        if cycle.position != "LATE":
            return False

        rsi = cycle.rsi_value
        if cycle.progress_percent > 80:
            if rsi > 70 or rsi < 30:
                return True

        if len(df) >= 20:
            close = df["close"].values
            sma = np.mean(close[-20:])
            if cycle.progress_percent > 85 and abs(close[-1] - sma) / sma > 0.02:
                return True

        return False
