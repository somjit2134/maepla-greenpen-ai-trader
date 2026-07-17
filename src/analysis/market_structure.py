from dataclasses import dataclass
from typing import Optional

import pandas as pd
import numpy as np

logger = __import__("logging").getLogger("market_structure")


@dataclass
class MarketStructure:
    condition: str = "RANGE"
    preference: str = "WAIT"
    swing_highs: list = None
    swing_lows: list = None
    last_high: Optional[float] = None
    last_low: Optional[float] = None
    hh_count: int = 0
    hl_count: int = 0
    lh_count: int = 0
    ll_count: int = 0
    detail: str = ""


class MarketStructureDetector:
    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def _find_pivots(self, high: np.ndarray, low: np.ndarray, left: int = 3, right: int = 3):
        length = len(high)
        pivot_highs = []
        pivot_lows = []

        for i in range(left, length - right):
            if all(high[i] >= high[i - j] for j in range(1, left + 1)) and \
               all(high[i] >= high[i + j] for j in range(1, right + 1)):
                pivot_highs.append((i, high[i]))

            if all(low[i] <= low[i - j] for j in range(1, left + 1)) and \
               all(low[i] <= low[i + j] for j in range(1, right + 1)):
                pivot_lows.append((i, low[i]))

        return pivot_highs, pivot_lows

    def detect(self, df: pd.DataFrame) -> MarketStructure:
        if df.empty or len(df) < 20:
            return MarketStructure(detail="Insufficient data")

        high = df["high"].values
        low = df["low"].values
        close = df["close"].values

        pivot_highs, pivot_lows = self._find_pivots(high, low, left=3, right=3)

        structure = MarketStructure(
            swing_highs=[p[1] for p in pivot_highs],
            swing_lows=[p[1] for p in pivot_lows],
        )

        if len(pivot_highs) < 2 or len(pivot_lows) < 2:
            structure.detail = "Not enough pivots detected"
            return structure

        recent_highs = [p[1] for p in pivot_highs[-4:]]
        recent_lows = [p[1] for p in pivot_lows[-4:]]

        structure.last_high = recent_highs[-1] if recent_highs else None
        structure.last_low = recent_lows[-1] if recent_lows else None

        hh = 0
        hl = 0
        lh = 0
        ll = 0

        for i in range(1, min(len(recent_highs), 4)):
            if recent_highs[i] > recent_highs[i - 1]:
                hh += 1
            else:
                lh += 1

        for i in range(1, min(len(recent_lows), 4)):
            if recent_lows[i] > recent_lows[i - 1]:
                hl += 1
            else:
                ll += 1

        structure.hh_count = hh
        structure.hl_count = hl
        structure.lh_count = lh
        structure.ll_count = ll

        bullish_score = hh + hl
        bearish_score = lh + ll

        if bullish_score >= 3 and bullish_score > bearish_score:
            structure.condition = "BULLISH"
            structure.preference = "BUY"
            structure.detail = f"Higher highs: {hh}, Higher lows: {hl}"
        elif bearish_score >= 3 and bearish_score > bullish_score:
            structure.condition = "BEARISH"
            structure.preference = "SELL"
            structure.detail = f"Lower highs: {lh}, Lower lows: {ll}"
        else:
            structure.detail = "Range / no clear structure"

        return structure
