from dataclasses import dataclass
from typing import Optional

import pandas as pd
import numpy as np


@dataclass
class PatternResult:
    pattern_name: str = ""
    detected: bool = False
    direction: str = ""  # "BULLISH", "BEARISH"
    strength: int = 0
    candle_idx: int = -1
    detail: str = ""


@dataclass
class PAnalysis:
    patterns: list = None
    bullish_confirmed: bool = False
    bearish_confirmed: bool = False
    overall: str = "NEUTRAL"
    detail: str = ""


class PriceActionDetector:
    def __init__(self):
        self.patterns = []

    def _is_bullish_engulfing(self, open_p, close_p, prev_open, prev_close):
        return close_p > open_p and prev_close < prev_open and close_p > prev_open and open_p < prev_close

    def _is_bearish_engulfing(self, open_p, close_p, prev_open, prev_close):
        return close_p < open_p and prev_close > prev_open and close_p < prev_open and open_p > prev_close

    def _is_pin_bar(self, open_p, high, low, close_p, body_ratio=0.3, wick_ratio=0.5):
        body = abs(close_p - open_p)
        total = high - low
        if total == 0:
            return None, 0

        lower_wick = min(open_p, close_p) - low
        upper_wick = high - max(open_p, close_p)

        if body / total <= body_ratio:
            if lower_wick / total >= wick_ratio and lower_wick > upper_wick * 2:
                return "BULLISH", 3
            elif upper_wick / total >= wick_ratio and upper_wick > lower_wick * 2:
                return "BEARISH", 3
        return None, 0

    def _is_inside_bar(self, open_p, close_p, prev_open, prev_close, prev_high, prev_low):
        return high <= prev_high and low >= prev_low

    high = low = None

    def detect(self, df: pd.DataFrame) -> PAnalysis:
        result = PAnalysis(patterns=[])
        if df.empty or len(df) < 3:
            return result

        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values

        last = len(closes) - 1
        patterns_detected = []

        bullish_count = 0
        bearish_count = 0

        for i in range(max(1, last - 5), last + 1):
            if i < 1:
                continue

            res = self._is_pin_bar(
                opens[i], highs[i], lows[i], closes[i]
            )
            if res and res[0]:
                pat = PatternResult(
                    pattern_name="Pin Bar" if res[0] == "BULLISH" else "Shooting Star",
                    detected=True,
                    direction=res[0],
                    strength=res[1],
                    candle_idx=i,
                    detail=f"{res[0]} pin bar at candle {i}",
                )
                patterns_detected.append(pat)
                if res[0] == "BULLISH":
                    bullish_count += res[1]
                else:
                    bearish_count += res[1]

            engulf_res = self._is_bullish_engulfing(
                opens[i], closes[i], opens[i - 1], closes[i - 1]
            )
            if engulf_res:
                pat = PatternResult(
                    pattern_name="Bullish Engulfing",
                    detected=True,
                    direction="BULLISH",
                    strength=3,
                    candle_idx=i,
                    detail=f"Bullish engulfing at candle {i}",
                )
                patterns_detected.append(pat)
                bullish_count += 3
                continue

            engulf_res = self._is_bearish_engulfing(
                opens[i], closes[i], opens[i - 1], closes[i - 1]
            )
            if engulf_res:
                pat = PatternResult(
                    pattern_name="Bearish Engulfing",
                    detected=True,
                    direction="BEARISH",
                    strength=3,
                    candle_idx=i,
                    detail=f"Bearish engulfing at candle {i}",
                )
                patterns_detected.append(pat)
                bearish_count += 3

        last_candle_body = abs(closes[last] - opens[last])
        last_candle_range = highs[last] - lows[last]

        if not patterns_detected:
            if last_candle_range > 0:
                lower_wick = min(opens[last], closes[last]) - lows[last]
                upper_wick = highs[last] - max(opens[last], closes[last])

                if lower_wick > last_candle_body * 2 and lower_wick > upper_wick * 2:
                    pat = PatternResult(
                        pattern_name="Long Lower Wick",
                        detected=True,
                        direction="BULLISH",
                        strength=2,
                        candle_idx=last,
                        detail="Long lower wick rejection",
                    )
                    patterns_detected.append(pat)
                    bullish_count += 2

                if upper_wick > last_candle_body * 2 and upper_wick > lower_wick * 2:
                    pat = PatternResult(
                        pattern_name="Long Upper Wick",
                        detected=True,
                        direction="BEARISH",
                        strength=2,
                        candle_idx=last,
                        detail="Long upper wick rejection",
                    )
                    patterns_detected.append(pat)
                    bearish_count += 2

            if closes[last] > opens[last] and closes[last] > closes[last - 1]:
                if len(closes) > 2 and closes[last - 1] > closes[last - 2]:
                    pat = PatternResult(
                        pattern_name="Consecutive Bullish",
                        detected=True,
                        direction="BULLISH",
                        strength=2,
                        candle_idx=last,
                        detail="Consecutive bullish candles",
                    )
                    patterns_detected.append(pat)
                    bullish_count += 2

            elif closes[last] < opens[last] and closes[last] < closes[last - 1]:
                if len(closes) > 2 and closes[last - 1] < closes[last - 2]:
                    pat = PatternResult(
                        pattern_name="Consecutive Bearish",
                        detected=True,
                        direction="BEARISH",
                        strength=2,
                        candle_idx=last,
                        detail="Consecutive bearish candles",
                    )
                    patterns_detected.append(pat)
                    bearish_count += 2

            if closes[last] > closes[last - 1] and lows[last] < lows[last - 1] and closes[last] > opens[last]:
                pat = PatternResult(
                    pattern_name="Bullish Rejection",
                    detected=True,
                    direction="BULLISH",
                    strength=2,
                    candle_idx=last,
                    detail="Bullish rejection at support",
                )
                patterns_detected.append(pat)
                bullish_count += 2

            elif closes[last] < closes[last - 1] and highs[last] > highs[last - 1] and closes[last] < opens[last]:
                pat = PatternResult(
                    pattern_name="Bearish Rejection",
                    detected=True,
                    direction="BEARISH",
                    strength=2,
                    candle_idx=last,
                    detail="Bearish rejection at resistance",
                )
                patterns_detected.append(pat)
                bearish_count += 2

        result.patterns = patterns_detected
        result.bullish_confirmed = bullish_count >= 3
        result.bearish_confirmed = bearish_count >= 3

        if result.bullish_confirmed and not result.bearish_confirmed:
            result.overall = "BULLISH"
        elif result.bearish_confirmed and not result.bullish_confirmed:
            result.overall = "BEARISH"
        elif result.bullish_confirmed and result.bearish_confirmed:
            if bullish_count > bearish_count:
                result.overall = "BULLISH"
            elif bearish_count > bullish_count:
                result.overall = "BEARISH"
            else:
                result.overall = "NEUTRAL"
        else:
            result.overall = "NEUTRAL"

        if patterns_detected:
            strongest = max(patterns_detected, key=lambda p: p.strength)
            result.detail = f"Strongest: {strongest.pattern_name} ({strongest.direction})"
        else:
            result.detail = "No significant patterns"

        return result
