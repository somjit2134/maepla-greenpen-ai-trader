"""
MT5 Autonomous Trading System - Price Action Signal Engine
============================================================
Detects candlestick patterns on completed candles only:
  1. Pin Bar - long rejection wick, small body
  2. Engulfing Pattern - bullish/bearish engulfing
  3. Rejection Candle - strong rejection from important frame
  4. False Breakout - break level then fail to continue
  5. Inside Bar - consolidation before breakout
  6. Consecutive candles - momentum confirmation

Signal Quality:
  A Grade: Frame + Cycle + Price Action aligned
  B Grade: Partial confirmation
  NO TRADE: Conflicting conditions
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from config import get_config

logger = logging.getLogger("price_action")


@dataclass
class Pattern:
    name: str = ""
    direction: str = ""
    strength: int = 0
    candle_idx: int = -1
    detail: str = ""


@dataclass
class PAResult:
    patterns: list = field(default_factory=list)
    bullish_confirmed: bool = False
    bearish_confirmed: bool = False
    bullish_count: int = 0
    bearish_count: int = 0
    overall: str = "NEUTRAL"
    signal_grade: str = "NO_TRADE"
    detail: str = ""


class PriceActionDetector:
    """Price Action Signal Engine - detect patterns on completed candles."""

    def __init__(self):
        self.cfg = get_config()

    def detect(self, df: pd.DataFrame) -> PAResult:
        result = PAResult(patterns=[])

        if df is None or df.empty or len(df) < 5:
            return result

        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values

        last = len(closes) - 1
        bullish_count = 0
        bearish_count = 0

        for i in range(max(1, last - 5), last + 1):
            pat = self._detect_pin_bar(opens[i], highs[i], lows[i], closes[i], i)
            if pat:
                result.patterns.append(pat)
                if pat.direction == "BULLISH":
                    bullish_count += pat.strength
                else:
                    bearish_count += pat.strength
                continue

            pat = self._detect_engulfing(opens, closes, i)
            if pat:
                result.patterns.append(pat)
                if pat.direction == "BULLISH":
                    bullish_count += pat.strength
                else:
                    bearish_count += pat.strength
                continue

            pat = self._detect_rejection(opens, highs, lows, closes, i)
            if pat:
                result.patterns.append(pat)
                if pat.direction == "BULLISH":
                    bullish_count += pat.strength
                else:
                    bearish_count += pat.strength

        pat = self._detect_false_breakout(highs, lows, closes, last)
        if pat:
            result.patterns.append(pat)
            if pat.direction == "BULLISH":
                bullish_count += pat.strength
            else:
                bearish_count += pat.strength

        pat = self._detect_consecutive(opens, closes, last)
        if pat:
            result.patterns.append(pat)
            if pat.direction == "BULLISH":
                bullish_count += pat.strength
            else:
                bearish_count += pat.strength

        result.bullish_count = bullish_count
        result.bearish_count = bearish_count
        result.bullish_confirmed = bullish_count >= 3
        result.bearish_confirmed = bearish_count >= 3

        if result.bullish_confirmed and not result.bearish_confirmed:
            result.overall = "BULLISH"
        elif result.bearish_confirmed and not result.bullish_confirmed:
            result.overall = "BEARISH"
        elif result.bullish_confirmed and result.bearish_confirmed:
            result.overall = "BULLISH" if bullish_count > bearish_count else "BEARISH"
        else:
            result.overall = "NEUTRAL"

        result.signal_grade = self._grade_signal(result)

        if result.patterns:
            strongest = max(result.patterns, key=lambda p: p.strength)
            result.detail = f"Strongest: {strongest.name} ({strongest.direction})"
        else:
            result.detail = "No significant patterns"

        logger.info(f"PA: {result.overall}, Grade: {result.signal_grade}, "
                     f"Bull:{bullish_count}, Bear:{bearish_count}")
        return result

    def _detect_pin_bar(self, o, h, l, c, idx) -> Optional[Pattern]:
        body = abs(c - o)
        total = h - l
        if total == 0:
            return None

        lower_wick = min(o, c) - l
        upper_wick = h - max(o, c)

        if body / total <= self.cfg.price_action.pin_bar_body_ratio:
            if lower_wick / total >= self.cfg.price_action.pin_bar_wick_ratio and lower_wick > upper_wick * 2:
                return Pattern("Pin Bar", "BULLISH", 3, idx, "Bullish pin bar")
            elif upper_wick / total >= self.cfg.price_action.pin_bar_wick_ratio and upper_wick > lower_wick * 2:
                return Pattern("Shooting Star", "BEARISH", 3, idx, "Bearish pin bar")
        return None

    def _detect_engulfing(self, opens, closes, idx) -> Optional[Pattern]:
        if idx < 1:
            return None

        o, c = opens[idx], closes[idx]
        po, pc = opens[idx - 1], closes[idx - 1]

        body = abs(c - o)
        prev_body = abs(pc - po)
        if prev_body == 0:
            return None

        if body / prev_body < self.cfg.price_action.engulfing_min_body:
            return None

        if c > o and pc < o and c > po:
            return Pattern("Bullish Engulfing", "BULLISH", 3, idx, "Bullish engulfing")
        elif c < o and pc > o and c < po:
            return Pattern("Bearish Engulfing", "BEARISH", 3, idx, "Bearish engulfing")
        return None

    def _detect_rejection(self, opens, highs, lows, closes, idx) -> Optional[Pattern]:
        o, h, l, c = opens[idx], highs[idx], lows[idx], closes[idx]
        total = h - l
        if total == 0:
            return None

        body = abs(c - o)
        lower_wick = min(o, c) - l
        upper_wick = h - max(o, c)

        if lower_wick > body * 2 and lower_wick > upper_wick * 1.5:
            return Pattern("Bullish Rejection", "BULLISH", 2, idx, "Long lower wick rejection")
        elif upper_wick > body * 2 and upper_wick > lower_wick * 1.5:
            return Pattern("Bearish Rejection", "BEARISH", 2, idx, "Long upper wick rejection")
        return None

    def _detect_false_breakout(self, highs, lows, closes, idx) -> Optional[Pattern]:
        if idx < self.cfg.price_action.false_breakout_bars:
            return None

        window = self.cfg.price_action.false_breakout_bars
        prev_high = np.max(highs[idx - window:idx])
        prev_low = np.min(lows[idx - window:idx])

        current_close = closes[idx]
        current_high = highs[idx]
        current_low = lows[idx]

        if current_high > prev_high and current_close < prev_high:
            return Pattern("False Breakout", "BEARISH", 3, idx, "False break above resistance")
        elif current_low < prev_low and current_close > prev_low:
            return Pattern("False Breakout", "BULLISH", 3, idx, "False break below support")
        return None

    def _detect_consecutive(self, opens, closes, idx) -> Optional[Pattern]:
        if idx < 2:
            return None

        bullish = all(closes[i] > opens[i] for i in range(idx - 2, idx + 1))
        bearish = all(closes[i] < opens[i] for i in range(idx - 2, idx + 1))

        if bullish and closes[idx] > closes[idx - 1] > closes[idx - 2]:
            return Pattern("Consecutive Bullish", "BULLISH", 2, idx, "3 consecutive bullish candles")
        elif bearish and closes[idx] < closes[idx - 1] < closes[idx - 2]:
            return Pattern("Consecutive Bearish", "BEARISH", 2, idx, "3 consecutive bearish candles")
        return None

    def _grade_signal(self, result: PAResult) -> str:
        confirmed = result.bullish_confirmed or result.bearish_confirmed
        count = max(result.bullish_count, result.bearish_count)

        if confirmed and count >= 6:
            return "A"
        elif confirmed and count >= 3:
            return "B"
        elif count >= 2:
            return "C"
        return "NO_TRADE"
