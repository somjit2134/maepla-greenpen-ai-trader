"""
MT5 Autonomous Trading System - Entry Decision Engine
======================================================
Combines all engines to produce a trade signal:
  Frame + Cycle + Trend + Price Action -> Signal
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from src.config import get_config
from src.analysis.frame_engine import FrameAnalyzer, FrameResult
from src.analysis.cycle_engine import CycleAnalyzer, CycleResult
from src.analysis.trend_engine import TrendAnalyzer, TrendResult
from src.analysis.price_action import PriceActionDetector, PAResult

logger = logging.getLogger("signal_engine")


@dataclass
class SignalResult:
    direction: str = "WAIT"
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    lot_size: float = 0.0
    confidence_score: float = 0.0
    signal_grade: str = "NO_TRADE"
    reasons: list = field(default_factory=list)
    risk_reward: float = 0.0
    frame: Optional[FrameResult] = None
    cycle: Optional[CycleResult] = None
    trend: Optional[TrendResult] = None
    price_action: Optional[PAResult] = None
    detail: str = ""


class SignalEngine:
    """Entry Decision Engine - combine all analysis into trade signal."""

    def __init__(self):
        self.cfg = get_config()
        self.frame_analyzer = FrameAnalyzer()
        self.cycle_analyzer = CycleAnalyzer()
        self.trend_analyzer = TrendAnalyzer()
        self.pa_detector = PriceActionDetector()

    def analyze(self, data: dict, bid: float, ask: float) -> SignalResult:
        mid = (bid + ask) / 2

        frame = self.frame_analyzer.analyze(data, mid)
        cycle = self.cycle_analyzer.analyze(data, mid)
        trend = self.trend_analyzer.analyze(data)
        h1 = data.get("H1")
        pa = self.pa_detector.detect(h1)

        buy_score, buy_reasons = self._score_direction("BUY", frame, cycle, trend, pa, bid, ask)
        sell_score, sell_reasons = self._score_direction("SELL", frame, cycle, trend, pa, bid, ask)

        if buy_score > sell_score and buy_score >= 6:
            direction = "BUY"
            score = buy_score
            reasons = buy_reasons
            entry, sl, tp1, tp2 = self._calculate_levels("BUY", mid, frame)
        elif sell_score > buy_score and sell_score >= 6:
            direction = "SELL"
            score = sell_score
            reasons = sell_reasons
            entry, sl, tp1, tp2 = self._calculate_levels("SELL", mid, frame)
        else:
            direction = "WAIT"
            score = max(buy_score, sell_score)
            reasons = buy_reasons if buy_score >= sell_score else sell_reasons
            entry = sl = tp1 = tp2 = 0.0

        rr = 0.0
        if direction != "WAIT" and abs(entry - sl) > 0:
            rr = round(abs(tp1 - entry) / abs(entry - sl), 2)

        grade = self._determine_grade(score, direction)

        result = SignalResult(
            direction=direction,
            entry_price=round(entry, 2),
            stop_loss=round(sl, 2),
            take_profit_1=round(tp1, 2),
            take_profit_2=round(tp2, 2),
            confidence_score=round(score, 1),
            signal_grade=grade,
            reasons=reasons,
            risk_reward=rr,
            frame=frame,
            cycle=cycle,
            trend=trend,
            price_action=pa,
        )

        result.detail = (
            f"{direction} | Score: {score:.1f}/10 | Grade: {grade} | "
            f"RR: {rr}:1 | Frame: {frame.overall_frame} | "
            f"Cycle: {cycle.position} | Trend: {trend.direction}"
        )

        logger.info(f"Signal: {result.detail}")
        return result

    def _score_direction(self, direction, frame, cycle, trend, pa, bid, ask) -> tuple:
        score = 0.0
        reasons = []

        frame_score = self._score_frame(direction, frame)
        score += frame_score
        if frame_score > 0:
            reasons.append(f"Frame OK ({frame.overall_frame})")

        cycle_score = self._score_cycle(direction, cycle)
        score += cycle_score
        if cycle_score > 0:
            reasons.append(f"Cycle OK ({cycle.position})")

        trend_score = self._score_trend(direction, trend)
        score += trend_score
        if trend_score > 0:
            reasons.append(f"Trend aligned ({trend.direction})")

        pa_score = self._score_pa(direction, pa)
        score += pa_score
        if pa_score > 0:
            reasons.append(f"PA confirmed ({pa.overall})")

        if not reasons:
            reasons.append("No confirming conditions")

        return round(score, 1), reasons

    def _score_frame(self, direction, frame: FrameResult) -> float:
        score = 0.0

        if direction == "BUY":
            if frame.sideway.in_range and (frame.sideway.range_low > 0):
                mid = frame.sideway.range_mid
                if mid > 0:
                    position_pct = (mid - frame.sideway.range_low) / frame.sideway.range_width if frame.sideway.range_width > 0 else 0.5
                    if position_pct < 0.4:
                        score += 2.0
                    elif position_pct < 0.5:
                        score += 1.0

            if frame.ath.is_rejecting or frame.ath.is_returning:
                score += 1.0

            if frame.cycle.position in ("BEGINNING", "MIDDLE"):
                score += 0.5

        elif direction == "SELL":
            if frame.sideway.in_range and frame.sideway.range_width > 0:
                mid = frame.sideway.range_mid
                if mid > 0:
                    position_pct = (mid - frame.sideway.range_low) / frame.sideway.range_width
                    if position_pct > 0.6:
                        score += 2.0
                    elif position_pct > 0.5:
                        score += 1.0

            if frame.ath.is_breaking:
                score += 1.0

            if frame.cycle.position in ("BEGINNING", "MIDDLE"):
                score += 0.5

        return min(score, 3.0)

    def _score_cycle(self, direction, cycle: CycleResult) -> float:
        if cycle.exhaustion_risk:
            return 0.0

        if cycle.position == "EARLY":
            return 2.0
        elif cycle.position == "MIDDLE":
            return 1.5
        return 0.0

    def _score_trend(self, direction, trend: TrendResult) -> float:
        if trend.direction == direction:
            return min(trend.alignment_score, 3.0)
        return 0.0

    def _score_pa(self, direction, pa: PAResult) -> float:
        if direction == "BUY" and pa.bullish_confirmed:
            return min(pa.bullish_count * 0.5, 2.0)
        elif direction == "SELL" and pa.bearish_confirmed:
            return min(pa.bearish_count * 0.5, 2.0)
        return 0.0

    def _calculate_levels(self, direction, price, frame: FrameResult):
        max_sl_distance = self.cfg.symbol.point * 500

        if direction == "BUY":
            entry = price
            sl = frame.sideway.range_low if frame.sideway.in_range else price - 15
            if frame.important_zones:
                support_zones = [z for z in frame.important_zones if z.level < price]
                if support_zones:
                    sl = min(sl, support_zones[0].level - 2)

            sl = max(sl, entry - max_sl_distance)
            risk = entry - sl
            tp1 = entry + risk * 2
            tp2 = entry + risk * 3

            if frame.sideway.in_range:
                tp1 = min(tp1, frame.sideway.range_high)
                tp2 = min(tp2, frame.sideway.range_high + risk)

        else:
            entry = price
            sl = frame.sideway.range_high if frame.sideway.in_range else price + 15
            if frame.important_zones:
                resistance_zones = [z for z in frame.important_zones if z.level > price]
                if resistance_zones:
                    sl = max(sl, resistance_zones[0].level + 2)

            sl = min(sl, entry + max_sl_distance)
            risk = sl - entry
            tp1 = entry - risk * 2
            tp2 = entry - risk * 3

            if frame.sideway.in_range:
                tp1 = max(tp1, frame.sideway.range_low)
                tp2 = max(tp2, frame.sideway.range_low - risk)

        return entry, sl, tp1, tp2

    def _determine_grade(self, score, direction) -> str:
        if direction == "WAIT":
            return "NO_TRADE"
        if score >= 9:
            return "A+"
        elif score >= 7:
            return "A"
        elif score >= 6:
            return "B+"
        elif score >= 5:
            return "B"
        return "NO_TRADE"
