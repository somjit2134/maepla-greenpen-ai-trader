"""
MT5 Autonomous Trading System - Market Frame Engine
=====================================================
Analyzes market context before every trade:
  1. ATH Frame - distance from All-Time High, breakout/rejection
  2. 1000 Point Cycle - beginning/middle/end of major swings
  3. Sideway Frame - consolidation detection
  4. Important Price Zones - psychological levels
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from config import get_config

logger = logging.getLogger("frame_engine")


@dataclass
class ATHFrame:
    ath: float = 0.0
    current_price: float = 0.0
    distance_percent: float = 0.0
    is_breaking: bool = False
    is_rejecting: bool = False
    is_returning: bool = False
    caution: bool = False
    detail: str = ""


@dataclass
class CycleFrame:
    swing_high: float = 0.0
    swing_low: float = 0.0
    total_range: float = 0.0
    progress_percent: float = 0.0
    position: str = "MIDDLE"
    detail: str = ""


@dataclass
class SidewayFrame:
    in_range: bool = False
    range_high: float = 0.0
    range_low: float = 0.0
    range_mid: float = 0.0
    range_width: float = 0.0
    breakout_up: bool = False
    breakout_down: bool = False
    false_breakout: bool = False
    detail: str = ""


@dataclass
class PriceZone:
    level: float = 0.0
    zone_type: str = ""
    distance: float = 0.0
    strength: int = 0


@dataclass
class FrameResult:
    ath: ATHFrame = field(default_factory=ATHFrame)
    cycle: CycleFrame = field(default_factory=CycleFrame)
    sideway: SidewayFrame = field(default_factory=SidewayFrame)
    important_zones: list = field(default_factory=list)
    overall_frame: str = "RANGE"
    trend_frame: str = "RANGE"
    range_frame: str = ""
    detail: str = ""


class FrameAnalyzer:
    """Market Frame Engine - analyze market context before trading."""

    def __init__(self):
        self.cfg = get_config()

    def analyze(self, data: dict[str, pd.DataFrame], current_price: float) -> FrameResult:
        result = FrameResult()

        result.ath = self._analyze_ath(data, current_price)
        result.cycle = self._analyze_cycle(data, current_price)
        result.sideway = self._analyze_sideway(data, current_price)
        result.important_zones = self._find_important_zones(current_price)

        result.overall_frame = self._determine_overall_frame(result)
        result.trend_frame = self._determine_trend_frame(data)
        result.range_frame = f"${result.sideway.range_low:.2f} - ${result.sideway.range_high:.2f}"

        result.detail = (
            f"ATH dist: {result.ath.distance_percent:.1f}%, "
            f"Cycle: {result.cycle.position}, "
            f"{'Sideway' if result.sideway.in_range else 'Trending'}, "
            f"Frame: {result.overall_frame}"
        )

        logger.info(f"Frame analysis: {result.detail}")
        return result

    def _analyze_ath(self, data: dict[str, pd.DataFrame], price: float) -> ATHFrame:
        """ATH Frame - detect distance from ATH, breakout, rejection."""
        d1 = data.get("D1")
        if d1 is None or d1.empty:
            return ATHFrame(current_price=price, detail="No D1 data")

        ath = d1["high"].max()
        distance = ath - price
        distance_pct = (distance / ath) * 100 if ath > 0 else 0

        is_breaking = price >= ath * 0.99
        is_rejecting = False
        is_returning = False

        if len(d1) >= 3:
            recent_high = d1["high"].iloc[-3:].max()
            if recent_high >= ath * 0.99 and price < recent_high * 0.98:
                is_rejecting = True
            if price < ath and d1["close"].iloc[-1] > d1["open"].iloc[-1]:
                is_returning = True

        caution = distance_pct <= self.cfg.frame.ath_caution_percent and distance > 0

        return ATHFrame(
            ath=ath,
            current_price=price,
            distance_percent=round(distance_pct, 2),
            is_breaking=is_breaking,
            is_rejecting=is_rejecting,
            is_returning=is_returning,
            caution=caution,
            detail=f"ATH: ${ath:.2f}, Dist: {distance_pct:.2f}%",
        )

    def _analyze_cycle(self, data: dict[str, pd.DataFrame], price: float) -> CycleFrame:
        """1000 Point Cycle Frame - measure position in major swing."""
        h4 = data.get("H4")
        d1 = data.get("D1")
        df = d1 if d1 is not None and not d1.empty else h4

        if df is None or df.empty:
            return CycleFrame(detail="No data")

        lookback = min(self.cfg.cycle.lookback_bars, len(df))
        recent = df.tail(lookback)

        swing_high = recent["high"].max()
        swing_low = recent["low"].min()
        total_range = swing_high - swing_low

        if total_range <= 0:
            return CycleFrame(detail="No range")

        progress = ((price - swing_low) / total_range) * 100
        progress = max(0, min(100, progress))

        if progress < self.cfg.cycle.early_threshold:
            position = "BEGINNING"
        elif progress < self.cfg.cycle.late_threshold:
            position = "MIDDLE"
        else:
            position = "END"

        return CycleFrame(
            swing_high=swing_high,
            swing_low=swing_low,
            total_range=round(total_range, 2),
            progress_percent=round(progress, 1),
            position=position,
            detail=f"Cycle: {position} ({progress:.0f}%), Range: {total_range:.0f}pts",
        )

    def _analyze_sideway(self, data: dict[str, pd.DataFrame], price: float) -> SidewayFrame:
        """Sideway Frame - detect consolidation areas on H4 for recent context."""
        h4 = data.get("H4")
        d1 = data.get("D1")
        df = h4 if h4 is not None and not h4.empty else d1

        if df is None or df.empty:
            return SidewayFrame(detail="No data")

        lookback = min(self.cfg.frame.sideway_min_bars, len(df))
        recent = df.tail(lookback)

        range_high = recent["high"].max()
        range_low = recent["low"].min()
        range_width = range_high - range_low
        range_mid = (range_high + range_low) / 2

        price_range_pct = (range_width / range_mid * 100) if range_mid > 0 else 0
        in_range = price_range_pct <= self.cfg.frame.sideway_range_percent * 20

        breakout_up = False
        breakout_down = False
        false_breakout = False

        if len(recent) >= 3:
            last_close = recent["close"].iloc[-1]
            prev_close = recent["close"].iloc[-2]

            if last_close > range_high and prev_close <= range_high:
                breakout_up = True
                if last_close < range_high + range_width * 0.1:
                    false_breakout = True

            if last_close < range_low and prev_close >= range_low:
                breakout_down = True
                if last_close > range_low - range_width * 0.1:
                    false_breakout = True

        return SidewayFrame(
            in_range=in_range,
            range_high=round(range_high, 2),
            range_low=round(range_low, 2),
            range_mid=round(range_mid, 2),
            range_width=round(range_width, 2),
            breakout_up=breakout_up,
            breakout_down=breakout_down,
            false_breakout=false_breakout,
            detail=f"Range: ${range_low:.2f}-${range_high:.2f}, Width: {price_range_pct:.1f}%",
        )

    def _find_important_zones(self, price: float) -> list:
        """Important Price Zones - psychological levels at round numbers."""
        step = self.cfg.frame.important_zone_step
        zones = []

        base = round(price / step) * step

        for offset in range(-10, 11):
            level = base + (offset * step)
            distance = abs(price - level)

            if distance <= step * 0.3:
                strength = 3
            elif distance <= step * 0.8:
                strength = 2
            elif distance <= step * 1.5:
                strength = 1
            else:
                strength = 0

            if strength > 0:
                zones.append(PriceZone(
                    level=round(level, 2),
                    zone_type="ROUND_NUMBER",
                    distance=round(distance, 2),
                    strength=strength,
                ))

        zones.sort(key=lambda z: z.distance)
        return zones[:5]

    def _determine_overall_frame(self, result: FrameResult) -> str:
        if result.sideway.breakout_up:
            return "BREAKOUT_UP"
        if result.sideway.breakout_down:
            return "BREAKOUT_DOWN"
        if result.sideway.in_range:
            return "RANGE"
        if result.ath.is_breaking:
            return "ATH_BREAK"
        if result.ath.is_rejecting:
            return "ATH_REJECT"
        return "TREND"

    def _determine_trend_frame(self, data: dict[str, pd.DataFrame]) -> str:
        d1 = data.get("D1")
        if d1 is None or d1.empty or len(d1) < 20:
            return "RANGE"

        close = d1["close"].values
        sma20 = np.mean(close[-20:])
        sma50 = np.mean(close[-50:]) if len(close) >= 50 else sma20

        if close[-1] > sma20 > sma50:
            return "BULLISH"
        elif close[-1] < sma20 < sma50:
            return "BEARISH"
        return "RANGE"
